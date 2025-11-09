from .state import OverallState, UserContext, UserMetadata, OnboardingStage, OnboardingResponse, UserIntent
from ..service import (
    generate_weekly_feedback,
    calculate_current_week_day,
    format_partial_weekly_feedback,
    format_no_record_message,
)
from ..service.onboarding import (
    handle_first_onboarding,
    process_extraction_result,
    extract_field_value,
    save_onboarding_conversation
)
from ..utils.models import get_chat_llm, get_summary_llm
from ..service.router.message_enhancer import extract_last_bot_message
from ..utils.utils import (
    format_conversation_history,
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
async def router_node(state: OverallState, db) -> Command[Literal["onboarding_agent_node", "service_router_node", "__end__"]]:
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
            # 온보딩 완료 당일 체크: created_at.date() == updated_at.date()
            if user_context.created_at and user_context.updated_at:
                created_date = user_context.created_at.date()
                updated_date = user_context.updated_at.date()

                if created_date == updated_date:
                    logger.info(f"[RouterNode] 🚫 온보딩 완료 당일 (created={created_date}, updated={updated_date}) - 일일기록 차단")
                    user_name = user_context.metadata.name if user_context.metadata else None
                    blocking_message = f"{user_name}님, 내일부터 업무기록을 시작할 수 있어요. 잊지 않도록 <3분커리어>가 알림할게요!" if user_name else "내일부터 업무기록을 시작할 수 있어요. 잊지 않도록 <3분커리어>가 알림할게요!"
                    return Command(update={"ai_response": blocking_message}, goto="__end__")

            logger.info(f"[RouterNode] ✅ 온보딩 완료 → service_router_node로 라우팅")
            return Command(goto="service_router_node")
        else:
            logger.info(f"[RouterNode] ⚠️ 온보딩 미완료 → onboarding_agent_node로 라우팅")
            return Command(goto="onboarding_agent_node")

    except Exception as e:
        logger.error(f"[RouterNode] ❌ Error: {e}")
        import traceback
        traceback.print_exc()
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
    logger.info(f"🔀 [ServiceRouter] 시작")

    from ..service import route_user_intent

    message = state["message"]
    user_context = state["user_context"]

    # 캐시된 데이터 사용
    cached_conv_state = state.get("cached_conv_state")
    cached_today_turns = state.get("cached_today_turns", [])

    logger.info(f"[ServiceRouter] message={message[:50]}")

    try:
        # 직전 봇 메시지 추출 및 컨텍스트 포함
        last_bot_message = extract_last_bot_message(cached_today_turns)
        enhanced_message = (
            f"[Previous bot]: {last_bot_message}\n[User]: {message}"
            if last_bot_message
            else message
        )

        # 비즈니스 로직: 의도 분류 + 라우팅 결정 (service 레이어)
        route, user_intent, classified_intent = await route_user_intent(
            enhanced_message, llm, user_context, db, cached_conv_state
        )

        # Command 생성
        logger.info(f"[ServiceRouter] 🔍 route={route}, user_intent={user_intent}, classified_intent={classified_intent}")

        update = {"user_intent": user_intent}
        if classified_intent is not None:  # daily의 경우 세부 의도 포함 (None이 아니면 모두 포함)
            update["classified_intent"] = classified_intent
            logger.info(f"[ServiceRouter] ✅ classified_intent 설정: {classified_intent}")
        else:
            logger.warning(f"[ServiceRouter] ⚠️ classified_intent가 None! route={route}")

        logger.info(f"[ServiceRouter] ✅ Command 반환 - goto={route}")
        return Command(update=update, goto=route)

    except Exception as e:
        logger.error(f"[ServiceRouter] ❌ Error: {e}, defaulting to daily_record")
        import traceback
        traceback.print_exc()
        # 에러 시 기본값: 일일 기록 (continue로 분류)
        return Command(
            update={
                "user_intent": UserIntent.DAILY_RECORD.value,
                "classified_intent": "continue"
            },
            goto="daily_agent_node"
        )


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
    from src.prompt.onboarding_questions import (
        get_next_field,
        format_completion_message
    )

    user_id = state["user_id"]
    message = state["message"]
    user_context = state["user_context"]

    print(f"🎯 [OnboardingAgent] 시작 - user_id: {user_id}, message: {message[:50]}")

    try:
        # ========================================
        # 1. 현재 상태 로드
        # ========================================
        current_metadata = user_context.metadata if user_context.metadata else UserMetadata()

        # 첫 온보딩 처리 (서비스 레이어로 분리)
        first_onboarding_result = await handle_first_onboarding(db, user_id, current_metadata)
        if first_onboarding_result["is_first"]:
            return Command(update={"ai_response": first_onboarding_result["ai_response"]}, goto="__end__")

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
        # 3. 대화 히스토리 로드 + LLM으로 정보 추출 (서비스 레이어)
        # ========================================
        # temp_data에서 최근 대화 히스토리 가져오기
        conv_state = await db.get_conversation_state(user_id)
        recent_messages = []
        if conv_state and conv_state.get("temp_data"):
            recent_messages = conv_state["temp_data"].get("onboarding_messages", [])[-6:]  # 최근 3턴

        # 대화 히스토리 포맷팅 - utils 함수 사용 (최근 1턴)
        history_text = format_conversation_history(recent_messages, max_turns=1)

        # LLM 호출하여 정보 추출 (서비스 레이어로 분리)
        extraction_result = await extract_field_value(
            message=message,
            target_field=target_field,
            history_text=history_text
        )

        print(f"🤖 [LLM 추출 결과] intent={extraction_result.intent}, value={extraction_result.extracted_value}, confidence={extraction_result.confidence}")

        # ========================================
        # 4. 추출 결과에 따른 처리 (서비스 레이어로 분리)
        # ========================================
        result = await process_extraction_result(
            db=db,
            user_id=user_id,
            message=message,
            extraction_result=extraction_result,
            current_metadata=current_metadata,
            target_field=target_field
        )

        ai_response = result["ai_response"]

        # 온보딩 완료 시 즉시 종료
        if result["is_completed"]:
            print(f"✅✅✅ [OnboardingAgent] 🎉🎉🎉 온보딩 완료, onboarding_messages 삭제됨")
            return Command(update={"ai_response": ai_response}, goto="__end__")

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
    logger.info(f"🔀 [DailyAgent] 노드 시작")

    from ..service import process_daily_record, save_daily_conversation

    user_id = state["user_id"]
    message = state["message"]
    user_context = state["user_context"]

    # 캐시된 데이터 사용
    cached_today_turns = state.get("cached_today_turns")

    logger.info(f"[DailyAgent] user_id={user_id}, message={message[:50]}")
    logger.info(f"[DailyAgent] 🔍 state.user_intent={state.get('user_intent')}")
    logger.info(f"[DailyAgent] 🔍 state.classified_intent={state.get('classified_intent')}")

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
        # 2. 의도 가져오기 (service_router에서 전달받음)
        # ========================================
        # daily_agent_node는 항상 service_router_node를 거치며,
        # service_router에서 모든 케이스에 대해 세부 의도를 분류하므로
        # classified_intent는 항상 존재함 (재분류 불필요)
        user_intent = state.get("classified_intent")
        logger.info(f"[DailyAgent] service_router에서 분류된 의도 사용: {user_intent}")

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

            from ..config.business_config import WEEKLY_CYCLE_DAYS

            # user_context에서 attendance_count 가져오기
            current_count = user_context.attendance_count

            # 0일차: 일일기록 시작 전
            if current_count == 0:
                logger.info(f"[WeeklyAgent] 0일차 (일일기록 시작 전)")
                ai_response = format_no_record_message()

                # 일반 대화로 저장
                await db.save_conversation_turn(user_id, message, ai_response, is_summary=False)

            # 1~6일차: 참고용 피드백 제공
            elif current_count % WEEKLY_CYCLE_DAYS != 0:
                # 현재 주차 내 일차 계산 (헬퍼 함수 사용)
                current_day_in_week = calculate_current_week_day(current_count)
                logger.info(f"[WeeklyAgent] {WEEKLY_CYCLE_DAYS}일 미달 (현재 {current_day_in_week}일차) → 참고용 피드백 제공")

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
