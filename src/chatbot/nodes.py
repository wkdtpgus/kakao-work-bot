from .state import OverallState, UserContext, UserMetadata, OnboardingStage, OnboardingResponse, UserIntent
from ..prompt.daily_record_prompt import DAILY_CONVERSATION_SYSTEM_PROMPT
from ..prompt.intent_classifier import SERVICE_ROUTER_SYSTEM_PROMPT, SERVICE_ROUTER_USER_PROMPT
from ..service import classify_user_intent, generate_daily_summary, generate_weekly_feedback
from ..service.weekly_fallback_generator import (
    calculate_current_week_day,
    format_partial_weekly_feedback,
    format_already_processed_message,
    format_no_record_message
)
from langchain_google_vertexai import ChatVertexAI
from ..utils.models import get_chat_llm, get_summary_llm
import logging
from typing import Literal
from langgraph.types import Command
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from datetime import datetime
import os
from langsmith import traceable

# Database repository functions
from ..database import (
    get_user_with_context,
    save_onboarding_metadata,
    complete_onboarding,
    check_and_reset_daily_count,
    increment_counts_with_check,
    get_today_conversations,
    handle_rejection_flag,
    set_weekly_summary_flag,
    update_daily_session_data,
    get_weekly_summary_flag,
    clear_weekly_summary_flag,
    prepare_daily_summary_data,
    prepare_weekly_feedback_data,
)

logger = logging.getLogger(__name__)


# =============================================================================
# 1. Router Node - 온보딩 완료 체크
# =============================================================================

@traceable(name="router_node")
async def router_node(state: OverallState, db) -> Command[Literal["onboarding_agent_node", "service_router_node"]]:
    """온보딩 완료 여부 체크 후 분기 + DB 쿼리 결과 캐싱"""
    user_id = state["user_id"]
    logger.info(f"🔀 [RouterNode] 시작 - user_id={user_id}")

    try:
        # Repository 함수로 사용자 정보 + UserContext 한 번에 로드
        user, user_context = await get_user_with_context(db, user_id)
        logger.info(f"[RouterNode] user_context.onboarding_stage={user_context.onboarding_stage}")

        # conversation_state 조회 (캐싱용)
        conv_state = await db.get_conversation_state(user_id)

        # 오늘 대화 히스토리 조회 (캐싱용 - 일반 대화는 최근 3턴, 요약은 전체 사용)
        today = datetime.now().date().isoformat()
        today_turns = await db.get_conversation_history_by_date_v2(user_id, today, limit=50)

        logger.info(f"[RouterNode] onboarding_complete={user_context.onboarding_stage == OnboardingStage.COMPLETED}, user_id={user_id}")

        # 온보딩 완료 여부에 따라 라우팅 + 캐싱
        if user_context.onboarding_stage == OnboardingStage.COMPLETED:
            return Command(
                update={
                    "user_context": user_context,
                    "cached_conv_state": conv_state,
                    "cached_today_turns": today_turns,
                },
                goto="service_router_node"
            )
        else:
            return Command(
                update={
                    "user_context": user_context,
                    "cached_conv_state": conv_state,
                },
                goto="onboarding_agent_node"
            )

    except Exception as e:
        logger.error(f"[RouterNode] Error: {e}")
        # 에러 시 기본 응답
        return Command(
            update={"ai_response": "죄송합니다. 오류가 발생했습니다."},
            goto="__end__"
        )


# =============================================================================
# 2. Service Router Node - 사용자 의도 파악
# =============================================================================

@traceable(name="service_router_node")
async def service_router_node(state: OverallState, llm, db) -> Command[Literal["daily_agent_node", "weekly_agent_node", "__end__"]]:
    """사용자 의도 파악: 일일 기록 vs 주간 피드백 (캐시 활용)

    일일 기록으로 라우팅하는 경우 세부 의도(summary/edit_summary/rejection/continue)도 분류하여 전달
    """
    message = state["message"]
    user_context = state["user_context"]
    user_id = state["user_id"]

    # 캐시된 데이터 사용
    cached_conv_state = state.get("cached_conv_state")
    cached_today_turns = state.get("cached_today_turns", [])

    logger.info(f"[ServiceRouter] message={message[:50]}")

    try:
        # 직전 봇 메시지 추출 (맥락 파악용)
        last_bot_message = None
        if cached_today_turns:
            # V2 스키마: {"user_message": "...", "ai_message": "..."}
            last_turn = cached_today_turns[-1] if cached_today_turns else None
            if last_turn and last_turn.get("ai_message"):
                last_bot_message = last_turn["ai_message"]

        # 의도 분류 시 직전 봇 메시지 포함
        enhanced_message = f"[Previous bot]: {last_bot_message}\n[User]: {message}" if last_bot_message else message

        # LLM으로 의도 분류 (온보딩 재시작 요청도 LLM이 처리)
        user_prompt = SERVICE_ROUTER_USER_PROMPT.format(message=enhanced_message)

        response = await llm.ainvoke([
            SystemMessage(content=SERVICE_ROUTER_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt)
        ])

        intent = response.content.strip().lower()

        # 거절 감지 (주간 요약 제안 거절 → 플래그 정리)
        if "rejection" in intent:
            logger.info(f"[ServiceRouter] Intent: rejection → 주간 요약 플래그 정리 + daily_agent_node")

            # Repository 함수 사용
            await handle_rejection_flag(db, user_id)

            return Command(
                update={
                    "user_intent": UserIntent.DAILY_RECORD.value,
                    "classified_intent": "rejection"  # daily_agent에서 재사용
                },
                goto="daily_agent_node"
            )

        # 주간 요약 수락 (7일차 달성 후 "네" 등)
        elif "weekly_acceptance" in intent:
            # cached_conv_state 사용 (DB 재조회 불필요)
            temp_data = cached_conv_state.get("temp_data", {}) if cached_conv_state else {}

            if temp_data.get("weekly_summary_ready"):
                logger.info(f"[ServiceRouter] Intent: weekly_acceptance (플래그 있음) → weekly_agent_node")
                return Command(update={"user_intent": UserIntent.WEEKLY_FEEDBACK.value}, goto="weekly_agent_node")
            else:
                # 주간 요약 제안 없이 긍정 응답만 한 경우 → 일반 대화로 처리
                logger.info(f"[ServiceRouter] Intent: weekly_acceptance BUT 플래그 없음 → daily_agent_node")
                return Command(update={"user_intent": UserIntent.DAILY_RECORD.value}, goto="daily_agent_node")
        # 주간 피드백 명시적 요청
        elif "weekly_feedback" in intent:
            logger.info(f"[ServiceRouter] Intent: weekly_feedback → weekly_agent_node")
            return Command(update={"user_intent": UserIntent.WEEKLY_FEEDBACK.value}, goto="weekly_agent_node")
        # 일일 기록 (기본값)
        else:
            logger.info(f"[ServiceRouter] Intent: daily_record → daily_agent_node")
            # 일일 기록 세부 의도 분류 (summary/edit_summary/rejection/continue/restart)
            from ..service import classify_user_intent
            # enhanced_message를 그대로 전달 (직전 봇 메시지 포함)
            detailed_intent = await classify_user_intent(enhanced_message, llm, user_context, db)
            logger.info(f"[ServiceRouter] 세부 의도 분류: {detailed_intent}")
            return Command(
                update={
                    "user_intent": UserIntent.DAILY_RECORD.value,
                    "classified_intent": detailed_intent  # daily_agent에서 재사용
                },
                goto="daily_agent_node"
            )

    except Exception as e:
        logger.error(f"[ServiceRouter] Error: {e}, defaulting to daily_record")
        # 에러 시 기본값: 일일 기록
        return Command(update={"user_intent": UserIntent.DAILY_RECORD.value}, goto="daily_agent_node")


# =============================================================================
# 3. Onboarding Agent Node - 온보딩 처리
# =============================================================================

@traceable(name="onboarding_agent_node")
async def onboarding_agent_node(state: OverallState, db, llm) -> Command[Literal["__end__"]]:
    """
    온보딩 대화 노드 (의도 추출 중심 방식)
    - LLM: 정보 추출만 수행 (ExtractionResponse)
    - 시스템: 질문 선택, 검증, 흐름 제어
    """
    from src.prompt.onboarding import EXTRACTION_SYSTEM_PROMPT, EXTRACTION_USER_PROMPT_TEMPLATE, FIELD_DESCRIPTIONS
    from src.prompt.onboarding_questions import (
        get_field_template, get_next_field,
        format_welcome_message, format_completion_message,
        FIELD_ORDER
    )
    from src.chatbot.state import ExtractionResponse, OnboardingIntent

    user_id = state["user_id"]
    message = state["message"]
    user_context = state["user_context"]

    print(f"🎯 [OnboardingAgent] 시작 - user_id: {user_id}, message: {message[:50]}")

    try:
        # ========================================
        # 1. 현재 상태 로드
        # ========================================
        current_metadata = user_context.metadata if user_context.metadata else UserMetadata()

        # 첫 온보딩인 경우 환영 메시지 (conversation_states로 체크)
        conv_state = await db.get_conversation_state(user_id)
        has_onboarding_messages = False
        if conv_state and conv_state.get("temp_data"):
            has_onboarding_messages = "onboarding_messages" in conv_state["temp_data"]

        is_first_onboarding = not has_onboarding_messages and all(getattr(current_metadata, field) is None for field in FIELD_ORDER)

        if is_first_onboarding:
            welcome_msg = format_welcome_message()
            # 첫 질문 가져오기
            first_template = get_field_template("name")
            first_question = first_template.get_question(1)
            ai_response = f"{welcome_msg}\n\n{first_question}"

            # 메타데이터 초기화 (field_attempts, field_status 저장)
            await save_onboarding_metadata(db, user_id, current_metadata)

            # 대화 히스토리 저장 (이미 save_onboarding_metadata에서 temp_data 병합했으므로 다시 로드)
            conv_state_updated = await db.get_conversation_state(user_id)
            existing_temp_data = conv_state_updated.get("temp_data", {}) if conv_state_updated else {}
            existing_temp_data["onboarding_messages"] = [{"role": "assistant", "content": ai_response}]

            await db.upsert_conversation_state(
                user_id,
                current_step="onboarding",
                temp_data=existing_temp_data
            )

            return Command(update={"ai_response": ai_response}, goto="__end__")

        # ========================================
        # 2. 다음 수집할 필드 결정
        # ========================================
        target_field = get_next_field(current_metadata.dict())

        if not target_field:
            # 모든 필드 완료
            await complete_onboarding(db, user_id)
            completion_msg = format_completion_message(current_metadata.name)
            logger.info(f"[OnboardingAgent] ✅ 온보딩 완료! user={user_id}")
            return Command(update={"ai_response": completion_msg}, goto="__end__")

        # ========================================
        # 3. 대화 히스토리 로드 + LLM으로 정보 추출
        # ========================================
        # temp_data에서 최근 대화 히스토리 가져오기
        conv_state = await db.get_conversation_state(user_id)
        recent_messages = []
        if conv_state and conv_state.get("temp_data"):
            recent_messages = conv_state["temp_data"].get("onboarding_messages", [])[-6:]  # 최근 3턴

        # 대화 히스토리 포맷팅
        history_text = ""
        if recent_messages:
            for msg in recent_messages[-2:]:  # 최근 1턴만 (봇 질문 + 사용자 답변)
                role = "봇" if msg["role"] == "assistant" else "사용자"
                history_text += f"{role}: {msg['content']}\n"

        field_description = FIELD_DESCRIPTIONS.get(target_field, "")
        extraction_prompt = EXTRACTION_USER_PROMPT_TEMPLATE.format(
            target_field=target_field,
            field_description=field_description,
            user_message=message[:300]  # 최대 300자
        )

        # 대화 히스토리를 포함한 프롬프트
        full_prompt = f"""**대화 컨텍스트:**
{history_text if history_text else "(첫 메시지)"}

{extraction_prompt}"""

        # LLM 호출 (structured output - ExtractionResponse)
        # llm 파라미터는 이미 OnboardingResponse로 설정되어 있으므로, 원본 LLM을 가져와야 함
        from ..utils.models import get_onboarding_llm
        base_llm = get_onboarding_llm()
        extraction_llm = base_llm.with_structured_output(ExtractionResponse)

        print(f"📤 [LLM 요청] 프롬프트:\n{full_prompt[:500]}...")
        extraction_result = await extraction_llm.ainvoke([
            SystemMessage(content=EXTRACTION_SYSTEM_PROMPT),
            HumanMessage(content=full_prompt)
        ])
        print(f"📥 [LLM 응답] type={type(extraction_result)}, value={extraction_result}")

        if extraction_result is None:
            print(f"⚠️ [LLM] None 반환 - 기본 처리")
            ai_response = "죄송합니다. 잠시 문제가 발생했어요. 다시 한 번 말씀해주시겠어요?"
            return Command(update={"ai_response": ai_response}, goto="__end__")

        print(f"🤖 [LLM 추출 결과] intent={extraction_result.intent}, value={extraction_result.extracted_value}, confidence={extraction_result.confidence}")

        # ========================================
        # 4. 추출 결과에 따른 처리
        # ========================================
        updated_metadata = current_metadata.copy()
        current_attempt = updated_metadata.field_attempts.get(target_field, 0)
        field_template = get_field_template(target_field)
        user_name = updated_metadata.name  # 질문에 사용할 이름

        # field_attempts의 의미: 이 필드에서 몇 번 시도했는가
        # 0 → 첫 시도 → 1차 질문 (get_question(1))
        # 1 → 두 번째 시도 → 2차 질문 (get_question(2))
        # 2 → 세 번째 시도 → 3차 질문 (get_question(3))

        if extraction_result.intent == OnboardingIntent.CLARIFICATION:
            # 명확화 요청 - 시도 횟수 증가하고 더 자세한 질문 제공
            updated_metadata.field_attempts[target_field] = current_attempt + 1
            new_attempt = updated_metadata.field_attempts[target_field]
            # 최대 3차 질문까지
            ai_response = field_template.get_question(min(new_attempt + 1, 3), name=user_name)

        elif extraction_result.intent == OnboardingIntent.INVALID:
            # 무관한 응답 - 시도 횟수 증가 후 재질문 또는 스킵
            updated_metadata.field_attempts[target_field] = current_attempt + 1
            new_attempt = updated_metadata.field_attempts[target_field]

            # 3회 이상 시도 시 스킵 처리
            if new_attempt >= 3:
                updated_metadata.field_status[target_field] = "insufficient"
                setattr(updated_metadata, target_field, f"[SKIPPED] 응답 거부")
                print(f"⚠️ [{target_field}] 3회 무관한 응답 - 스킵 처리")

                # 다음 필드로 이동
                next_field = get_next_field(updated_metadata.dict())

                if next_field:
                    next_template = get_field_template(next_field)
                    ai_response = next_template.get_question(1, name=updated_metadata.name)
                else:
                    # 온보딩 완료
                    await complete_onboarding(db, user_id)
                    ai_response = format_completion_message(updated_metadata.name)

                await save_onboarding_metadata(db, user_id, updated_metadata)
                return Command(update={"ai_response": ai_response}, goto="__end__")
            else:
                # 재질문
                print(f"⚠️ [{target_field}] 무관한 응답 ({new_attempt}/3회) - 재질문")
                ai_response = field_template.get_question(min(new_attempt + 1, 3), name=user_name)
                await save_onboarding_metadata(db, user_id, updated_metadata)
                return Command(update={"ai_response": ai_response}, goto="__end__")

        elif extraction_result.intent == OnboardingIntent.ANSWER:
            # 답변 제공됨
            extracted_value = extraction_result.extracted_value
            confidence = extraction_result.confidence

            # 신뢰도 체크: 0.5 미만이면 명확화 필요
            if confidence < 0.5:
                updated_metadata.field_attempts[target_field] = current_attempt + 1
                new_attempt = updated_metadata.field_attempts[target_field]
                print(f"⚠️ [{target_field}] 신뢰도 낮음 (conf={confidence:.2f}) - 명확화 요청")
                ai_response = field_template.get_question(min(new_attempt + 1, 3), name=user_name)
                # 메타데이터 저장 후 종료
                await save_onboarding_metadata(db, user_id, updated_metadata)
                return Command(update={"ai_response": ai_response}, goto="__end__")

            # 신입 특수 처리
            if target_field == "total_years" and extracted_value and "신입" in extracted_value:
                updated_metadata.total_years = "신입"
                updated_metadata.job_years = "신입"
                updated_metadata.field_status["total_years"] = "filled"
                updated_metadata.field_status["job_years"] = "filled"
                updated_metadata.field_attempts["total_years"] = current_attempt + 1
                updated_metadata.field_attempts["job_years"] = 0  # job_years는 건너뛰었으므로 0
                print(f"✅ [신입 감지] total_years, job_years 모두 '신입'으로 설정")

                # career_goal로 이동
                next_field = "career_goal"
            else:
                # 검증
                if field_template.validate(extracted_value):
                    setattr(updated_metadata, target_field, extracted_value)
                    updated_metadata.field_status[target_field] = "filled"
                    updated_metadata.field_attempts[target_field] = current_attempt + 1
                    print(f"✅ [{target_field}] 값 저장: {extracted_value}")

                    # 다음 필드
                    next_field = get_next_field(updated_metadata.dict())
                else:
                    # 검증 실패
                    updated_metadata.field_attempts[target_field] = current_attempt + 1
                    print(f"❌ [{target_field}] 검증 실패: {extracted_value}")
                    next_field = target_field  # 같은 필드 재시도

            # 시도 횟수 체크 (3회 초과 시 스킵)
            if updated_metadata.field_attempts.get(target_field, 0) >= 3:
                updated_metadata.field_status[target_field] = "insufficient"
                setattr(updated_metadata, target_field, f"[INSUFFICIENT] {extracted_value or message[:50]}")
                next_field = get_next_field(updated_metadata.dict())

            # 다음 질문 생성
            if next_field == target_field:
                # 같은 필드 재시도 (검증 실패 케이스)
                next_attempt_count = updated_metadata.field_attempts.get(next_field, 0)
                # attempts가 1이면 2차 질문, 2이면 3차 질문
                next_question = field_template.get_question(min(next_attempt_count + 1, 3), name=user_name)
                ai_response = next_question
            elif next_field:
                # 다른 필드로 이동 (성공 케이스)
                next_template = get_field_template(next_field)
                # 새 필드는 아직 시도 안 했으므로 1차 질문
                # name이 방금 저장되었을 수 있으니 updated_metadata에서 다시 가져옴
                next_question = next_template.get_question(1, name=updated_metadata.name)

                # 간단한 확인 메시지 + 다음 질문
                if getattr(updated_metadata, target_field):
                    ai_response = f"{next_question}"
                else:
                    ai_response = next_question
            else:
                # 완료 - 마지막 필드까지 저장 후 온보딩 완료 처리
                print(f"💾 [OnboardingAgent] 온보딩 완료 - save_onboarding_metadata 호출 전")
                print(f"💾 [OnboardingAgent] updated_metadata.important_thing = {updated_metadata.important_thing}")
                await save_onboarding_metadata(db, user_id, updated_metadata)
                print(f"💾 [OnboardingAgent] save_onboarding_metadata 완료")
                await complete_onboarding(db, user_id)
                ai_response = format_completion_message(updated_metadata.name)
                print(f"✅✅✅ [OnboardingAgent] 🎉🎉🎉 온보딩 완료 (NEW CODE), onboarding_messages 삭제됨")
                return Command(update={"ai_response": ai_response}, goto="__end__")

        else:  # INVALID
            # 무관한 내용 - 현재 필드 재질문
            updated_metadata.field_attempts[target_field] = current_attempt + 1
            new_attempt = updated_metadata.field_attempts[target_field]
            # new_attempt가 1이면 2차 질문, 2이면 3차 질문
            ai_response = field_template.get_question(min(new_attempt + 1, 3), name=user_name)

        # ========================================
        # 5. 메타데이터 저장 (온보딩 진행 중만)
        # ========================================
        await save_onboarding_metadata(db, user_id, updated_metadata)
        print(f"✅ [OnboardingAgent] 메타데이터 저장 완료")

        # 대화 히스토리 저장 (온보딩 진행 중만)
        conv_state = await db.get_conversation_state(user_id)
        recent_messages = []
        if conv_state and conv_state.get("temp_data"):
            recent_messages = conv_state["temp_data"].get("onboarding_messages", [])[-6:]

        recent_messages.append({"role": "user", "content": message})
        recent_messages.append({"role": "assistant", "content": ai_response})
        recent_messages = recent_messages[-6:]  # 최근 3턴만 유지

        await db.upsert_conversation_state(
            user_id,
            current_step="onboarding",
            temp_data={"onboarding_messages": recent_messages}
        )

        return Command(update={"ai_response": ai_response}, goto="__end__")

    except Exception as e:
        logger.error(f"[OnboardingAgent] Error: {e}")
        import traceback
        traceback.print_exc()

        fallback_response = "죄송합니다. 다시 말씀해주시겠어요?"
        return Command(update={"ai_response": fallback_response}, goto="__end__")


# =============================================================================
# 4. Daily Agent Node - 일일 기록 처리 (턴 카운팅 제거, 대화 횟수 기반)
# =============================================================================

@traceable(name="daily_agent_node")
async def daily_agent_node(state: OverallState, db) -> Command[Literal["__end__", "weekly_agent_node"]]:
    """일일 기록 대화 (대화 횟수 기반, 5회 이상 시 요약 제안) - 캐시 활용"""

    user_id = state["user_id"]
    message = state["message"]
    user_context = state["user_context"]

    # 캐시된 데이터 사용
    cached_conv_state = state.get("cached_conv_state")
    cached_today_turns = state.get("cached_today_turns")

    logger.info(f"[DailyAgent] user_id={user_id}, message={message[:50]}")

    try:
        # ========================================
        # 1. 초기 데이터 로드 (캐시 활용 + Repository 함수)
        # ========================================
        today = datetime.now().date().isoformat()

        # cached_today_turns가 있으면 사용, 없으면 조회 (fallback)
        if cached_today_turns is not None:
            today_turns = cached_today_turns
            conv_state = cached_conv_state
            logger.info(f"[DailyAgent] 캐시된 today_turns 사용 ({len(today_turns)}개)")
        else:
            # Repository 함수로 한 번에 조회 (fallback)
            today_turns, conv_state = await get_today_conversations(db, user_id)
            logger.info(f"[DailyAgent] today_turns DB 조회 ({len(today_turns)}개)")

        # conv_state는 repository 함수에서 반환받은 것 사용
        logger.info(f"[DailyAgent] 초기 데이터 로드 완료 (캐시 활용, 오늘 대화: {len(today_turns)}개)")

        # 날짜 변경 체크 및 리셋 (Repository 함수)
        current_attendance, was_reset = await check_and_reset_daily_count(db, user_id)

        if was_reset:
            logger.info(f"[DailyAgent] ✅ daily_record_count 리셋됨")
            # user_context 업데이트
            user_context.daily_record_count = 0
            user_context.attendance_count = current_attendance

        metadata = user_context.metadata
        llm = get_chat_llm()

        # 현재 세션의 대화 횟수 계산 (user + bot 쌍 = 1회)
        current_session_count = user_context.daily_session_data.get("conversation_count", 0)
        logger.info(f"[DailyAgent] 현재 대화 횟수: {current_session_count}")

        # 요약 여부 추적 (공통 저장 로직용)
        is_summary_response = False
        summary_type_value = None
        is_edit_summary = False  # 요약 수정 여부 (카운트 증가 판단용)

        # ========================================
        # 사용자 의도 분류: 요약 요청 vs 거절 vs 재시작 vs 일반 대화
        # service_router에서 이미 분류된 경우 재사용, 아니면 새로 분류
        # ========================================
        user_intent = state.get("classified_intent")
        if not user_intent:
            # service_router를 거치지 않은 경우에만 분류 (직접 호출 시)
            user_intent = await classify_user_intent(message, llm, user_context, db)
        else:
            logger.info(f"[DailyAgent] service_router에서 분류된 의도 재사용: {user_intent}")

        # 오늘 기록 없이 요약 요청한 경우
        if "no_record_today" in user_intent:
            logger.info(f"[DailyAgent] 오늘 날짜 기록 없이 요약 요청 → 거부")
            user_context.daily_session_data = {}
            ai_response_final = f"{metadata.name}님, 오늘의 일일기록을 먼저 진행해주세요! 오늘 하신 업무에 대해 이야기 나눠볼까요?"

        # 거절 (요약 제안 거절 → 세션 초기화하고 새 기록 시작 안내)
        elif "rejection" in user_intent:
            logger.info(f"[DailyAgent] 거절 감지 → 세션 초기화")
            user_context.daily_session_data = {}
            ai_response_final = f"알겠습니다, {metadata.name}님! 다시 시작할 때 편하게 말씀해주세요."

        # 대화 종료 요청
        elif "end_conversation" in user_intent:
            logger.info(f"[DailyAgent] 대화 종료 요청")
            user_context.daily_session_data = {}  # 세션 종료
            ai_response_final = f"좋아요 {metadata.name}님, 오늘도 수고하셨습니다! 내일 다시 만나요 😊"

        # 수정 불필요 (요약 만족 → 세션 종료)
        # 🚨 중요: 요약이 방금 생성된 경우에만 종료 처리
        elif "no_edit_needed" in user_intent and user_context.daily_session_data.get("last_summary_at"):
            # 요약 직후 → 세션 종료
            logger.info(f"[DailyAgent] 수정 불필요 (요약 후) → 깔끔하게 마무리")
            user_context.daily_session_data = {}  # 세션 종료
            ai_response_final = f"좋아요 {metadata.name}님, 오늘도 수고하셨습니다! 내일 다시 만나요 😊"

        # 요약 수정 요청 (방금 생성된 요약에 추가 정보 반영)
        elif "edit_summary" in user_intent:
            logger.info(f"[DailyAgent] 요약 수정 요청 → 사용자 피드백을 시스템 프롬프트에 명시적으로 주입")

            # 요약 재생성 (오늘 대화만 사용, 사용자 수정 요청은 user_correction으로 전달)
            # user_correction을 통해 시스템 프롬프트에 명시적으로 주입됨
            input_data = await prepare_daily_summary_data(
                db,
                user_id,
                today_turns,
                user_correction=message  # 사용자의 수정 요청을 명시적으로 전달
            )
            output = await generate_daily_summary(input_data, llm)
            ai_response = output.summary_text
            current_attendance_count = input_data.attendance_count

            # 요약 플래그 설정
            is_summary_response = True
            summary_type_value = 'daily'
            is_edit_summary = True  # 요약 수정은 카운트에 포함

            # last_summary_at 업데이트 + conversation_count 리셋
            user_context.daily_session_data["last_summary_at"] = datetime.now().isoformat()
            user_context.daily_session_data["conversation_count"] = 0
            logger.info(f"[DailyAgent] 요약 수정 완료 → conversation_count 리셋")

            # 7일차 체크 (Repository 함수 사용)
            current_daily_count = user_context.daily_record_count

            if current_attendance_count > 0 and current_attendance_count % 7 == 0 and current_daily_count >= 5:
                logger.info(f"[DailyAgent] 🎉 7일차 달성! (수정된 요약, attendance={current_attendance_count}, daily={current_daily_count})")
                ai_response_with_suggestion = f"{ai_response}\n\n🎉 **7일차 달성!** 주간 요약도 보여드릴까요?"

                await db.save_conversation_turn(user_id, message, ai_response_with_suggestion, is_summary=True, summary_type='daily')

                # Repository 함수로 주간 요약 플래그 설정
                await set_weekly_summary_flag(db, user_id, current_attendance_count, user_context.daily_session_data)

                return Command(
                    update={"ai_response": ai_response_with_suggestion, "user_context": user_context},
                    goto="__end__"
                )

            ai_response_final = ai_response

        # 요약 요청
        elif "summary" in user_intent:
            logger.info(f"[DailyAgent] 요약 생성 요청")

            # 요약 생성 (오늘 대화만 사용)
            input_data = await prepare_daily_summary_data(db, user_id, today_turns)
            output = await generate_daily_summary(input_data, llm)
            ai_response = output.summary_text
            current_attendance_count = input_data.attendance_count

            # 요약 플래그 설정
            is_summary_response = True
            summary_type_value = 'daily'

            # last_summary_at 플래그 저장 + conversation_count 리셋 (다음 5회 대화 후 다시 제안 가능)
            user_context.daily_session_data["last_summary_at"] = datetime.now().isoformat()
            user_context.daily_session_data["conversation_count"] = 0
            logger.info(f"[DailyAgent] 요약 생성 완료 → conversation_count 리셋")

            # 7일차 체크 (Repository 함수 사용)
            current_daily_count = user_context.daily_record_count

            if current_attendance_count > 0 and current_attendance_count % 7 == 0 and current_daily_count >= 5:
                logger.info(f"[DailyAgent] 🎉 7일차 달성! (attendance={current_attendance_count}, daily={current_daily_count})")

                # 즉시 응답 (지연 없이)
                ai_response_with_suggestion = f"{ai_response}\n\n🎉 **7일차 달성!** 주간 요약도 보여드릴까요?"

                # 대화 저장
                await db.save_conversation_turn(user_id, message, ai_response_with_suggestion, is_summary=True, summary_type='daily')

                # Repository 함수로 주간 요약 플래그 설정
                await set_weekly_summary_flag(db, user_id, current_attendance_count, user_context.daily_session_data)

                logger.info(f"[DailyAgent] 데일리 요약 완료, 주간 요약은 사용자 요청 시 생성")

                return Command(
                    update={"ai_response": ai_response_with_suggestion, "user_context": user_context},
                    goto="__end__"
                )

            # 7일차 아니면 세션 유지하고 종료 (같은 날 계속 대화 가능)
            ai_response_final = ai_response

        # 재시작 요청 (명시적으로 새 세션 시작)
        elif "restart" in user_intent:
            logger.info(f"[DailyAgent] 재시작 요청 → 세션 초기화")
            user_context.daily_session_data = {}
            ai_response_final = f"{metadata.name}님, 새로운 일일 기록을 시작하겠습니다! 오늘은 어떤 업무를 하셨나요?"

        # 일반 대화 (질문 생성)
        else:
            logger.info(f"[DailyAgent] 일반 대화 진행 ({current_session_count + 1}회차)")

            # 5회 이상 대화 시 요약 제안
            if current_session_count >= 5:
                logger.info(f"[DailyAgent] 5회 이상 대화 완료 → 요약 제안")
                ai_response_final = f"{metadata.name}님, 오늘도 많은 이야기 나눠주셨네요! 지금까지 내용을 정리해드릴까요?"
            else:
                # 최근 3턴만 조회 (성능 최적화)
                recent_turns = await db.get_recent_turns_v2(user_id, limit=3)
                logger.info(f"[DailyAgent] 최근 대화 조회: {len(recent_turns)}턴")

                # 자연스러운 질문 생성
                system_prompt = DAILY_CONVERSATION_SYSTEM_PROMPT.format(
                    name=metadata.name or "없음",
                    job_title=metadata.job_title or "없음",
                    total_years=metadata.total_years or "없음",
                    job_years=metadata.job_years or "없음",
                    career_goal=metadata.career_goal or "없음",
                    project_name=metadata.project_name or "없음",
                    recent_work=metadata.recent_work or "없음"
                )

                messages = [SystemMessage(content=system_prompt)]
                # 최근 3턴 사용 (메모리 최적화)
                for turn in recent_turns:
                    messages.append(HumanMessage(content=turn["user_message"]))
                    messages.append(AIMessage(content=turn["ai_message"]))
                messages.append(HumanMessage(content=message))

                response = await llm.ainvoke(messages)
                ai_response_final = response.content

                # 대화 횟수 증가
                user_context.daily_session_data["conversation_count"] = current_session_count + 1
                logger.info(f"[DailyAgent] ✅ 질문 생성 완료, 대화 횟수: {current_session_count} → {current_session_count + 1}")

        # ========================================
        # 공통: 대화 저장 + daily_record_count 증가 + attendance_count 체크 (Repository 함수)
        # ========================================
        await db.save_conversation_turn(
            user_id, message, ai_response_final,
            is_summary=is_summary_response,
            summary_type=summary_type_value if is_summary_response else None
        )

        # 🚨 중요: 요약 생성 시에만 카운트 증가 안 함
        # - 요약 수정(edit_summary)은 실제 대화 내용을 반영하므로 카운트 O
        # - 요약 생성(summary)은 기존 대화의 정리이므로 카운트 X
        should_increment = True
        if is_summary_response and not is_edit_summary:
            # 요약 생성(summary)만 카운트 제외
            should_increment = False
            logger.info(f"[DailyAgent] 요약 생성 - daily_record_count 증가 안 함")

        if should_increment:
            # Repository 함수로 카운트 증가 (daily_record_count + attendance_count 자동 처리)
            updated_daily_count, new_attendance = await increment_counts_with_check(db, user_id)

            if new_attendance:
                logger.info(f"[DailyAgent] 🎉 5회 달성! attendance_count 증가: {new_attendance}일차")
                user_context.attendance_count = new_attendance

            logger.info(f"[DailyAgent] daily_record_count 업데이트: {updated_daily_count}회")
        else:
            # 요약 생성 시 카운트 증가 안 함 (현재 값 유지)
            updated_daily_count = user_context.daily_record_count

        # Repository 함수로 세션 데이터 업데이트
        await update_daily_session_data(
            db,
            user_id,
            user_context.daily_session_data,
            current_step="daily_recording" if user_context.daily_session_data else "daily_summary_completed"
        )

        logger.info(f"[DailyAgent] 완료: conversation_count={current_session_count}, daily_record_count={updated_daily_count}")

        return Command(update={"ai_response": ai_response_final, "user_context": user_context}, goto="__end__")

    except Exception as e:
        logger.error(f"[DailyAgent] Error: {e}")
        import traceback
        traceback.print_exc()

        fallback_response = "처리 중 오류가 발생했습니다. 다시 시도해주세요."
        await db.save_conversation_turn(user_id, message, fallback_response, is_summary=False)

        return Command(update={"ai_response": fallback_response}, goto="__end__")


# =============================================================================
# 5. Weekly Agent Node - 주간 피드백 생성 (7일차 자동 or 사용자 수동 요청)
# =============================================================================

@traceable(name="weekly_agent_node")
async def weekly_agent_node(state: OverallState, db) -> Command[Literal["__end__"]]:
    """주간 피드백 생성 및 DB 저장 (Repository 함수 활용)

    호출 경로:
    1. service_router_node → 7일차 달성 후 사용자 수락 시 (weekly_acceptance)
    2. service_router_node → 사용자가 수동으로 주간 피드백 요청 (weekly_feedback)
    """

    user_id = state["user_id"]
    message = state["message"]
    user_context = state["user_context"]

    logger.info(f"[WeeklyAgent] user_id={user_id}, message={message}")

    # LLM 인스턴스 가져오기 (캐시됨) - 주간요약은 summary_llm 사용 (max_tokens 300)
    llm = get_summary_llm()

    try:
        # Repository 함수로 주간 요약 플래그 확인
        is_ready, stored_attendance_count = await get_weekly_summary_flag(db, user_id)

        # 7일차 자동 트리거 (플래그만 확인, daily_agent_node에서 이미 검증됨)
        if is_ready and stored_attendance_count:
            logger.info(f"[WeeklyAgent] 7일차 주간요약 생성 (attendance_count={stored_attendance_count})")

            # 주간 피드백 생성
            input_data = await prepare_weekly_feedback_data(db, user_id)
            output = await generate_weekly_feedback(input_data, llm)
            weekly_summary = output.feedback_text

            # Repository 함수로 플래그 정리
            await clear_weekly_summary_flag(db, user_id)

            ai_response = weekly_summary

        # 수동 요청인 경우 (7일 미달 체크)
        else:
            logger.info(f"[WeeklyAgent] 수동 요청")

            # user_context에서 attendance_count 가져오기
            current_count = user_context.attendance_count

            # 0일차: 일일기록 시작 전
            if current_count == 0:
                logger.info(f"[WeeklyAgent] 0일차 (일일기록 시작 전)")
                ai_response = format_no_record_message()

                # 일반 대화로 저장
                await db.save_conversation_turn(user_id, message, ai_response, is_summary=False)

            # 1~6일차: 참고용 피드백 제공
            elif current_count % 7 != 0:
                # 현재 주차 내 일차 계산 (헬퍼 함수 사용)
                current_day_in_week = calculate_current_week_day(current_count)
                logger.info(f"[WeeklyAgent] 7일 미달 (현재 {current_day_in_week}일차) → 참고용 피드백 제공")

                # 임시 피드백 생성
                input_data = await prepare_weekly_feedback_data(db, user_id)
                output = await generate_weekly_feedback(input_data, llm)
                partial_feedback = output.feedback_text

                # 헬퍼 함수로 응답 포맷팅
                ai_response = format_partial_weekly_feedback(current_day_in_week, partial_feedback)

                # 참고용은 summary_type='daily'로 저장
                await db.save_conversation_turn(user_id, message, ai_response, is_summary=True, summary_type='daily')

            # 7, 14, 21일차 but 플래그 없음: 이미 확인했거나 거절한 경우
            else:
                logger.info(f"[WeeklyAgent] 7일차지만 플래그 없음 → 이미 처리됨")
                ai_response = format_already_processed_message()

                # 일반 대화로 저장
                await db.save_conversation_turn(user_id, message, ai_response, is_summary=False)

            # 조기 리턴 (정식 주간요약과 분리)
            logger.info(f"[WeeklyAgent] 참고용 피드백 완료: {ai_response[:50]}...")
            return Command(update={"ai_response": ai_response}, goto="__end__")

        # 정식 주간요약 대화 저장 (is_ready=True인 경우만)
        await db.save_conversation_turn(user_id, message, ai_response, is_summary=True, summary_type='weekly')

        logger.info(f"[WeeklyAgent] 주간 피드백 생성 완료: {ai_response[:50]}...")

        return Command(update={"ai_response": ai_response}, goto="__end__")

    except Exception as e:
        logger.error(f"[WeeklyAgent] Error: {e}")
        import traceback
        traceback.print_exc()

        fallback_response = "주간 피드백 생성 중 오류가 발생했습니다."
        await db.save_conversation_turn(user_id, message, fallback_response, is_summary=False)

        return Command(update={"ai_response": fallback_response}, goto="__end__")
