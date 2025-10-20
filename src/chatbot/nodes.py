from .state import OverallState, UserContext, UserMetadata, OnboardingStage, OnboardingResponse, UserIntent
from ..utils.utils import get_system_prompt, format_user_prompt
from ..prompt.onboarding import ONBOARDING_SYSTEM_PROMPT, ONBOARDING_USER_PROMPT_TEMPLATE
from ..prompt.daily_record_prompt import DAILY_CONVERSATION_SYSTEM_PROMPT
from ..prompt.intent_classifier import SERVICE_ROUTER_SYSTEM_PROMPT, SERVICE_ROUTER_USER_PROMPT
from ..service import classify_user_intent, generate_daily_summary, generate_weekly_feedback
from ..service.weekly_fallback_generator import (
    calculate_current_week_day,
    format_partial_weekly_feedback,
    format_already_processed_message,
    format_no_record_message
)
from langchain_openai import ChatOpenAI
from ..utils.models import CHAT_MODEL_CONFIG
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
    """온보딩 대화 + 정보 추출 + DB 저장 (Repository 함수 활용)"""
    user_id = state["user_id"]
    message = state["message"]
    user_context = state["user_context"]

    print(f"🎯 [OnboardingAgent] 시작 - user_id: {user_id}, message: {message[:50]}")

    try:
        # ========================================
        # 1. 초기 데이터 로드
        # ========================================
        # 온보딩 대화 히스토리 로드 (temp_data에서, 최근 3턴 = 6개 메시지)
        conv_state = await db.get_conversation_state(user_id)
        recent_messages = []

        if conv_state and conv_state.get("temp_data"):
            # temp_data에 저장된 온보딩 메시지 (최근 3턴)
            recent_messages = conv_state["temp_data"].get("onboarding_messages", [])[-6:]
            logger.info(f"[OnboardingAgent] 온보딩 히스토리 로드: {len(recent_messages)}개 ({len(recent_messages)//2}턴)")

        # 프롬프트 구성
        current_metadata = user_context.metadata if user_context.metadata else UserMetadata()
        current_state = current_metadata.dict()

        # 🆕 현재 타겟 필드와 시도 횟수 정보 추가
        FIELD_ORDER = ["name", "job_title", "total_years", "job_years", "career_goal",
                       "project_name", "recent_work", "job_meaning", "important_thing"]

        target_field = None
        for field in FIELD_ORDER:
            if not getattr(current_metadata, field):
                if current_metadata.field_status.get(field) != "skipped":
                    target_field = field
                    break

        current_attempt = current_metadata.field_attempts.get(target_field, 0) + 1 if target_field else 1

        system_prompt = get_system_prompt()
        user_prompt = format_user_prompt(
            message, current_state, "", recent_messages,
            target_field=target_field, current_attempt=current_attempt
        )

        logger.info(f"[OnboardingAgent] target={target_field}, attempt={current_attempt}, message={message[:50]}")

        # LLM 호출 (structured output)
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ])

        # 정보 추출
        updated_metadata = user_context.metadata.copy() if user_context.metadata else UserMetadata()

        # 🆕 현재 타겟 필드 결정 (최우선 null 필드)
        FIELD_ORDER = ["name", "job_title", "total_years", "job_years", "career_goal",
                       "project_name", "recent_work", "job_meaning", "important_thing"]

        current_target_field = None
        for field in FIELD_ORDER:
            if not getattr(updated_metadata, field):
                # skipped 필드는 건너뛰기
                if updated_metadata.field_status.get(field) != "skipped":
                    current_target_field = field
                    break

        if isinstance(response, OnboardingResponse):
            # 필드 업데이트
            if response.name: updated_metadata.name = response.name
            if response.job_title: updated_metadata.job_title = response.job_title
            if response.total_years: updated_metadata.total_years = response.total_years
            if response.job_years: updated_metadata.job_years = response.job_years
            if response.career_goal: updated_metadata.career_goal = response.career_goal
            if response.project_name: updated_metadata.project_name = response.project_name
            if response.recent_work: updated_metadata.recent_work = response.recent_work
            if response.job_meaning: updated_metadata.job_meaning = response.job_meaning
            if response.important_thing: updated_metadata.important_thing = response.important_thing

            # 🆕 LLM이 판단한 field_status 병합
            if response.field_status:
                updated_metadata.field_status.update(response.field_status)

            # 🆕 현재 타겟 필드의 시도 횟수 증가 (명확화 요청이 아닐 때만)
            if current_target_field:
                if response.is_clarification_request:
                    print(f"💬 [OnboardingAgent] 명확화 요청 감지 - 시도 횟수 유지 (field: {current_target_field})")
                else:
                    # ✅ 원본 current_metadata에서 현재 시도 횟수 가져오기 (updated_metadata는 복사본이라 0으로 초기화됨)
                    current_attempts = current_metadata.field_attempts.get(current_target_field, 0)
                    updated_metadata.field_attempts[current_target_field] = current_attempts + 1
                    print(f"📊 [OnboardingAgent] {current_target_field} 시도 횟수: {current_attempts} → {current_attempts + 1}")

                    # 3회 시도 후에도 null이면 스킵 (단, 유저의 마지막 답변은 보존)
                    if current_attempts + 1 >= 3 and not getattr(updated_metadata, current_target_field):
                        # 유저가 뭔가 말했다면 그것을 "INSUFFICIENT: {답변}" 형태로 저장
                        user_raw_answer = message.strip()
                        if user_raw_answer and user_raw_answer not in ["건너뛰기", "모름", "나중에", "skip"]:
                            setattr(updated_metadata, current_target_field, f"[INSUFFICIENT] {user_raw_answer}")
                            updated_metadata.field_status[current_target_field] = "insufficient"
                        else:
                            # 유저가 명시적으로 스킵 요청
                            updated_metadata.field_status[current_target_field] = "skipped"

            ai_response = response.response
        else:
            ai_response = str(response)

        # Repository 함수로 메타데이터 저장 (users + conversation_states.temp_data 동시 저장)
        await save_onboarding_metadata(db, user_id, updated_metadata)

        print(f"✅ [OnboardingAgent] 메타데이터 저장 완료 (Repository 함수)")

        # 온보딩 대화 히스토리 업데이트 (최근 3턴만 유지)
        onboarding_messages = recent_messages.copy()
        onboarding_messages.append({"role": "user", "content": message})
        onboarding_messages.append({"role": "assistant", "content": ai_response})

        # 최근 3턴(6개 메시지)만 유지
        onboarding_messages = onboarding_messages[-6:]

        # temp_data 업데이트
        conv_state_updated = await db.get_conversation_state(user_id)
        temp_data = conv_state_updated.get("temp_data", {}) if conv_state_updated else {}
        temp_data["onboarding_messages"] = onboarding_messages

        await db.upsert_conversation_state(user_id, current_step="onboarding", temp_data=temp_data)
        logger.info(f"[OnboardingAgent] 대화 히스토리 저장: {len(onboarding_messages)//2}턴")

        # 온보딩 완료 체크 (skipped/insufficient 모두 완료로 간주)
        REQUIRED_FIELDS = ["name", "job_title", "total_years", "job_years", "career_goal",
                          "project_name", "recent_work", "job_meaning", "important_thing"]

        filled_or_handled = []
        for field in REQUIRED_FIELDS:
            value = getattr(updated_metadata, field)
            status = updated_metadata.field_status.get(field)
            # 값이 있거나, skipped/insufficient 상태면 완료로 간주
            is_handled = value is not None or status in ["skipped", "insufficient"]
            filled_or_handled.append(is_handled)

        is_onboarding_complete = all(filled_or_handled)

        # 이미 완료된 유저가 재진입한 경우 프롬프트가 처리하도록 넘김
        was_already_complete = user_context.onboarding_stage == OnboardingStage.COMPLETED

        # 온보딩 완료 시 특별 메시지 (이미 완료된 유저 제외 - 프롬프트가 재시작 요청 처리)
        if is_onboarding_complete and not was_already_complete:
            # Repository 함수로 온보딩 완료 처리
            await complete_onboarding(db, user_id)
            logger.info(f"[OnboardingAgent] ✅ onboarding_completed = True (Repository 함수)")

            completion_message = f"""🎉 {updated_metadata.name}님, 온보딩이 완료되었어요!

지금까지 공유해주신 소중한 이야기를 바탕으로, 앞으로 {updated_metadata.name}님의 커리어 여정을 함께하겠습니다.

📝 일일 기록 시작하기

이제부터는 매일 업무를 기록하며 성장을 돌아볼 수 있어요. 아래처럼 자유롭게 말씀해주세요:

• "오늘은 ___를 했어요"
• "오늘 어려웠던 점: ___"
• "오늘 배운 점: ___"

제가 {updated_metadata.name}님의 이야기를 듣고, 더 깊이 생각해볼 수 있는 질문들을 드릴게요.

언제든 편하게 말씀해주세요!
대시보드 링크: 추가추가!!!!"""

            ai_response = completion_message
            logger.info(f"[OnboardingAgent] 온보딩 완료! user={user_id}")

        # 온보딩 완료 시 대화 히스토리 초기화 (일일기록은 깨끗한 상태로 시작)
        # 온보딩 중에는 대화 턴을 저장하지 않음
        # (완료 후 complete_onboarding()에서 자동 삭제되므로 불필요)
        logger.info(f"[OnboardingAgent] 응답: {ai_response[:50]}... (대화 턴 저장 스킵)")

        return Command(update={"ai_response": ai_response}, goto="__end__")

    except Exception as e:
        logger.error(f"[OnboardingAgent] Error: {e}")
        import traceback
        traceback.print_exc()

        fallback_response = "죄송합니다. 오류가 발생했습니다."
        # 온보딩 중에는 대화 턴 저장하지 않음

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
        llm = ChatOpenAI(**CHAT_MODEL_CONFIG, api_key=os.getenv("OPENAI_API_KEY"))

        # 현재 세션의 대화 횟수 계산 (user + bot 쌍 = 1회)
        current_session_count = user_context.daily_session_data.get("conversation_count", 0)
        logger.info(f"[DailyAgent] 현재 대화 횟수: {current_session_count}")

        # 요약 여부 추적 (공통 저장 로직용)
        is_summary_response = False
        summary_type_value = None

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

        # 요약 수정 요청 (방금 생성된 요약에 추가 정보 반영)
        elif "edit_summary" in user_intent:
            logger.info(f"[DailyAgent] 요약 수정 요청 → 추가 정보 반영 후 재생성")

            # 현재 메시지를 대화 목록에 추가 (수정 요청 내용 반영)
            today_turns_with_current = today_turns + [
                {"role": "user", "content": message, "created_at": datetime.now().isoformat()}
            ]

            # 요약 재생성 (오늘 대화 + 현재 메시지 포함)
            input_data = await prepare_daily_summary_data(db, user_id, today_turns_with_current)
            output = await generate_daily_summary(input_data, llm)
            ai_response = output.summary_text
            current_attendance_count = input_data.attendance_count

            # 요약 플래그 설정
            is_summary_response = True
            summary_type_value = 'daily'

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

        # Repository 함수로 카운트 증가 (daily_record_count + attendance_count 자동 처리)
        updated_daily_count, new_attendance = await increment_counts_with_check(db, user_id)

        if new_attendance:
            logger.info(f"[DailyAgent] 🎉 5회 달성! attendance_count 증가: {new_attendance}일차")
            user_context.attendance_count = new_attendance

        logger.info(f"[DailyAgent] daily_record_count 업데이트: {updated_daily_count}회")

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

    # LLM 인스턴스 생성
    llm = ChatOpenAI(**CHAT_MODEL_CONFIG, api_key=os.getenv("OPENAI_API_KEY"))

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
