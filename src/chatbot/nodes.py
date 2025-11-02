from .state import OverallState, UserContext, UserMetadata, OnboardingStage, OnboardingResponse, UserIntent
from ..service import (
    classify_user_intent,
    generate_weekly_feedback,
    calculate_current_week_day,
    format_partial_weekly_feedback,
    format_no_record_message,
)
from ..utils.models import get_chat_llm, get_summary_llm
from ..utils.utils import (
    extract_last_bot_message,
    enhance_message_with_context,
    format_conversation_history,
    save_onboarding_conversation,
    error_command,
)
import logging
from typing import Literal
from langgraph.types import Command
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from datetime import datetime
from langsmith import traceable

# Database repository functions
from ..database import (
    save_onboarding_metadata,
    complete_onboarding,
    check_and_reset_daily_count,
    get_today_conversations,
    get_weekly_summary_flag,
    clear_weekly_summary_flag,
    prepare_weekly_feedback_data,
)

logger = logging.getLogger(__name__)


# =============================================================================
# 1. Router Node - 온보딩 완료 체크
# =============================================================================

@traceable(name="router_node")
async def router_node(state: OverallState, db) -> Command[Literal["onboarding_agent_node", "service_router_node"]]:
    """온보딩 완료 여부 체크 후 분기 (캐시는 graph_manager에서 이미 로드됨)"""
    user_id = state["user_id"]
    logger.info(f"🔀 [RouterNode] 시작 - user_id={user_id}")

    try:
        # graph_manager에서 이미 로드된 캐시 사용
        user_context = state["user_context"]
        logger.info(f"[RouterNode] user_context.onboarding_stage={user_context.onboarding_stage}")
        logger.info(f"[RouterNode] onboarding_complete={user_context.onboarding_stage == OnboardingStage.COMPLETED}, user_id={user_id}")

        # 온보딩 완료 여부에 따라 라우팅 (State는 이미 캐시 포함)
        if user_context.onboarding_stage == OnboardingStage.COMPLETED:
            return Command(goto="service_router_node")
        else:
            return Command(goto="onboarding_agent_node")

    except Exception as e:
        logger.error(f"[RouterNode] Error: {e}")
        # 에러 시 기본 응답 - utils 함수 사용
        return error_command("죄송합니다. 오류가 발생했습니다.")


# =============================================================================
# 2. Service Router Node - 사용자 의도 파악
# =============================================================================

@traceable(name="service_router_node")
async def service_router_node(state: OverallState, llm, db) -> Command[Literal["daily_agent_node", "weekly_agent_node", "__end__"]]:
    """사용자 의도 파악: 일일 기록 vs 주간 피드백 (캐시 활용)

    일일 기록으로 라우팅하는 경우 세부 의도(summary/edit_summary/rejection/continue)도 분류하여 전달
    """
    from ..service import route_user_intent

    message = state["message"]
    user_context = state["user_context"]

    # 캐시된 데이터 사용
    cached_conv_state = state.get("cached_conv_state")
    cached_today_turns = state.get("cached_today_turns", [])

    logger.info(f"[ServiceRouter] message={message[:50]}")

    try:
        # 직전 봇 메시지 추출 (맥락 파악용) - utils 함수 사용
        last_bot_message = extract_last_bot_message(cached_today_turns)

        # 의도 분류 시 직전 봇 메시지 포함 - utils 함수 사용
        enhanced_message = enhance_message_with_context(message, last_bot_message)

        # 비즈니스 로직: 의도 분류 + 라우팅 결정 (service 레이어)
        route, user_intent, classified_intent = await route_user_intent(
            enhanced_message, llm, user_context, db, cached_conv_state
        )

        # Command 생성
        update = {"user_intent": user_intent}
        if classified_intent:  # daily의 경우 세부 의도 포함
            update["classified_intent"] = classified_intent

        return Command(update=update, goto=route)

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

        # 대화 히스토리 포맷팅 - utils 함수 사용 (최근 1턴)
        history_text = format_conversation_history(recent_messages, max_turns=1)

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

        # 대화 히스토리 저장 (온보딩 진행 중만) - utils 함수 사용
        await save_onboarding_conversation(db, user_id, message, ai_response, max_history=6)

        return Command(update={"ai_response": ai_response}, goto="__end__")

    except Exception as e:
        logger.error(f"[OnboardingAgent] Error: {e}")
        import traceback
        traceback.print_exc()

        fallback_response = "죄송합니다. 다시 말씀해주시겠어요?"
        return Command(update={"ai_response": fallback_response}, goto="__end__")


# =============================================================================
# 4. Daily Agent Node - 일일 기록 처리 (Service 레이어 활용)
# =============================================================================

@traceable(name="daily_agent_node")
async def daily_agent_node(state: OverallState, db) -> Command[Literal["__end__", "weekly_agent_node"]]:
    """일일 기록 대화 처리 (비즈니스 로직은 service 레이어로 분리)

    Orchestration:
    1. 랭그래프 state에서 초기 데이터 로드 (캐시 활용) 및 goto라우팅, state 업데이트
    2. 의도 분류 (service_router에서 분류된 경우 재사용)
    3. 비즈니스 로직 처리 (service/daily_record_handler)
    4. 대화 저장 + 카운트 증가 (service/daily_record_handler)
    """
    from ..service import process_daily_record, save_daily_conversation

    user_id = state["user_id"]
    message = state["message"]
    user_context = state["user_context"]

    # 캐시된 데이터 사용
    cached_today_turns = state.get("cached_today_turns")

    logger.info(f"[DailyAgent] user_id={user_id}, message={message[:50]}")

    try:
        # ========================================
        # 1. 초기 준비 (캐시 활용 + 날짜 리셋)
        # ========================================
        # cached_today_turns가 있으면 사용, 없으면 조회 (fallback)
        if cached_today_turns is not None:
            today_turns = cached_today_turns
            logger.info(f"[DailyAgent] 캐시된 today_turns 사용 ({len(today_turns)}개)")
        else:
            today_turns, _ = await get_today_conversations(db, user_id)
            logger.info(f"[DailyAgent] today_turns DB 조회 ({len(today_turns)}개)")

        # 날짜 변경 체크 및 리셋
        current_attendance, was_reset = await check_and_reset_daily_count(db, user_id)

        if was_reset:
            logger.info(f"[DailyAgent] ✅ daily_record_count 리셋됨")
            user_context.daily_record_count = 0
            user_context.attendance_count = current_attendance

        llm = get_chat_llm()

        # ========================================
        # 2. 의도 분류 (service_router에서 분류된 경우 재사용)
        # ========================================
        user_intent = state.get("classified_intent")
        if not user_intent:
            # service_router를 거치지 않은 경우에만 분류
            user_intent = await classify_user_intent(message, llm, user_context, db)
        else:
            logger.info(f"[DailyAgent] service_router에서 분류된 의도 재사용: {user_intent}")

        # ========================================
        # 3. 비즈니스 로직 처리 (service 레이어)
        # ========================================
        result = await process_daily_record(
            db=db,
            user_id=user_id,
            message=message,
            user_intent=user_intent,
            user_context=user_context,
            cached_today_turns=today_turns,
            llm=llm
        )

        # 조기 종료 필요 시 (7일차 제안 등)
        if result.early_return:
            return Command(update={"ai_response": result.ai_response, "user_context": user_context}, goto="__end__")

        # ========================================
        # 4. 대화 저장 + 카운트 증가 + 세션 업데이트 (service 레이어)
        # ========================================
        updated_daily_count, new_attendance = await save_daily_conversation(
            db, user_id, message, result, user_context
        )

        logger.info(f"[DailyAgent] 완료: daily_record_count={updated_daily_count}")

        return Command(update={"ai_response": result.ai_response, "user_context": user_context}, goto="__end__")

    except Exception as e:
        logger.error(f"[DailyAgent] Error: {e}")
        import traceback
        traceback.print_exc()

        fallback_response = "처리 중 오류가 발생했습니다. 다시 시도해주세요."
        await db.save_conversation_turn(user_id, message, fallback_response, is_summary=False)

        return Command(update={"ai_response": fallback_response}, goto="__end__")


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
    metadata = user_context.metadata  # UserMetadata 추출

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
            # user_data 캐시 전달 (중복 DB 쿼리 방지)
            user_data = {
                "name": metadata.name,
                "job_title": metadata.job_title,
                "career_goal": metadata.career_goal
            }
            input_data = await prepare_weekly_feedback_data(db, user_id, user_data=user_data)
            output = await generate_weekly_feedback(input_data, llm)
            weekly_summary = output.feedback_text

            # Repository 함수로 플래그 정리
            await clear_weekly_summary_flag(db, user_id)
            logger.info(f"[WeeklyAgent] 정식 주간요약 완료 → 플래그 정리")

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
                # user_data 캐시 전달 (중복 DB 쿼리 방지)
                user_data = {
                    "name": metadata.name,
                    "job_title": metadata.job_title,
                    "career_goal": metadata.career_goal
                }
                input_data = await prepare_weekly_feedback_data(db, user_id, user_data=user_data)
                output = await generate_weekly_feedback(input_data, llm)
                partial_feedback = output.feedback_text

                # 헬퍼 함수로 응답 포맷팅
                ai_response = format_partial_weekly_feedback(current_day_in_week, partial_feedback)

                # 참고용은 summary_type='daily'로 저장
                await db.save_conversation_turn(user_id, message, ai_response, is_summary=True, summary_type='daily')

            # 7, 14, 21일차: 정식 주간요약 제공 (플래그 없어도 OK)
            else:
                logger.info(f"[WeeklyAgent] 7일차 이후 수동 요청 → 정식 주간요약 제공")

                # 정식 주간요약 생성
                user_data = {
                    "name": metadata.name,
                    "job_title": metadata.job_title,
                    "career_goal": metadata.career_goal
                }
                input_data = await prepare_weekly_feedback_data(db, user_id, user_data=user_data)
                output = await generate_weekly_feedback(input_data, llm)
                ai_response = output.feedback_text

                # 플래그가 있으면 정리 (이전에 거절했다가 다시 요청한 경우)
                if is_ready:
                    await clear_weekly_summary_flag(db, user_id)
                    logger.info(f"[WeeklyAgent] 수동 요청이지만 플래그 있음 → 플래그 정리")

                # 정식 주간요약으로 저장
                await db.save_conversation_turn(user_id, message, ai_response, is_summary=True, summary_type='weekly')

            # 수동 요청 조기 리턴 (0일차, 1-6일차, 7일차 이후)
            logger.info(f"[WeeklyAgent] 수동 요청 완료: {ai_response[:50]}...")
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
