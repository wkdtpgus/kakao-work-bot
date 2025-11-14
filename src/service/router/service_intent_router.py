"""
Service Intent Router
서비스 라우팅을 위한 최상위 의도 분류 모듈

역할:
- 최상위 서비스 의도 분류 (daily_record / weekly_feedback / weekly_acceptance / rejection)
- 주간 요약 플래그 체크 및 거절 처리
- 일일 기록 세부 의도 분류 위임 (daily_intent_classifier 사용)
- 라우팅 결정 (daily_agent_node vs weekly_agent_node)
"""

import logging
from typing import Tuple, Optional
from langchain_core.messages import SystemMessage, HumanMessage
from ...prompt.intent_prompts import (
    SERVICE_ROUTER_SYSTEM_PROMPT,
    SERVICE_ROUTER_USER_PROMPT,
    SERVICE_ROUTER_USER_PROMPT_WITH_WEEKLY_CONTEXT
)

logger = logging.getLogger(__name__)


async def classify_service_intent(
    message: str,
    llm,
    cached_conv_state: Optional[dict] = None
) -> Tuple[str, bool]:
    """
    최상위 서비스 의도 분류 (daily vs weekly vs rejection)

    Args:
        message: 사용자 메시지 (맥락 포함 가능)
        llm: LangChain LLM 인스턴스
        cached_conv_state: 캐시된 conversation_state (weekly 플래그 체크용)

    Returns:
        (intent, has_weekly_flag)
        - intent: "daily_record" | "weekly_feedback" | "weekly_acceptance" | "rejection"
        - has_weekly_flag: 주간 요약 플래그 존재 여부
    """
    try:
        # ===== 플래그/상태 기반 우선 라우팅 =====
        # weekly_summary_ready 플래그 또는 weekly_summary_pending 상태이면 주간 요약 제안 상태
        has_weekly_flag = False
        if cached_conv_state:
            temp_data = cached_conv_state.get("temp_data", {})
            current_step = cached_conv_state.get("current_step", "")
            has_weekly_flag = (
                temp_data.get("weekly_summary_ready", False) or
                current_step == "weekly_summary_pending"
            )

        # ===== LLM 기반 의도 분류 =====
        # 플래그 있음: 주간요약 제안 컨텍스트 포함 3-way 분류 (weekly_acceptance / rejection / daily_record)
        # 플래그 없음: 일반 4-way 분류 (daily_record / weekly_feedback / weekly_acceptance / rejection)
        if has_weekly_flag:
            # 주간 요약 제안 상태 → 컨텍스트 포함 프롬프트 사용
            user_prompt = SERVICE_ROUTER_USER_PROMPT_WITH_WEEKLY_CONTEXT.format(message=message)
            logger.info(f"[IntentRouter] 플래그 있음 → 주간요약 컨텍스트 포함 LLM 분류")
        else:
            # 일반 상태 → 기본 프롬프트 사용
            user_prompt = SERVICE_ROUTER_USER_PROMPT.format(message=message)
            logger.info(f"[IntentRouter] 플래그 없음 → 일반 LLM 분류")

        response = await llm.ainvoke([
            SystemMessage(content=SERVICE_ROUTER_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt)
        ])

        intent = response.content.strip().lower()

        logger.info(f"[IntentRouter] LLM 분류 결과: {intent}, weekly_flag={has_weekly_flag}")

        return intent, has_weekly_flag

    except Exception as e:
        logger.error(f"[IntentRouter] LLM 의도 분류 실패: {e}, 기본값 daily_record 반환")
        return "daily_record", False


async def route_user_intent(
    message: str,
    llm,
    user_context,
    db,
    cached_conv_state: Optional[dict] = None
) -> Tuple[str, str, Optional[str]]:
    """
    사용자 의도 분류 + 라우팅 결정

    Args:
        message: 컨텍스트가 포함된 사용자 메시지
        llm: LangChain LLM 인스턴스
        user_context: UserContext 객체
        db: Database 인스턴스
        cached_conv_state: 캐시된 conversation_state

    Returns:
        (route, user_intent, classified_intent)
        - route: 이동할 노드 ("daily_agent_node" | "weekly_agent_node")
        - user_intent: UserIntent enum 값 ("daily_record" | "weekly_feedback")
        - classified_intent: 세부 의도 (daily의 경우) 또는 None
    """
    from ...chatbot.state import UserIntent
    from ..daily.intent_classifier import classify_user_intent
    from ...database.conversation_repository import handle_rejection_flag

    # 1. 최상위 의도 분류
    intent, has_weekly_flag = await classify_service_intent(message, llm, cached_conv_state)

    # 2. 거절 처리 (주간 요약 제안 거절 → 플래그 정리)
    if intent == "rejection":
        logger.info(f"[IntentRouter] 거절 감지 → 주간 요약 플래그 정리")
        await handle_rejection_flag(db, user_context.user_id)

        return "daily_agent_node", UserIntent.DAILY_RECORD.value, "rejection"

    # 3. 주간 요약 수락 (7일차 달성 후 "네" 등)
    elif intent == "weekly_acceptance":
        if has_weekly_flag:
            logger.info(f"[IntentRouter] 주간 요약 수락 (플래그 있음) → weekly_agent_node")
            return "weekly_agent_node", UserIntent.WEEKLY_FEEDBACK.value, None
        else:
            # 플래그 없으면 일반 대화로 처리 (세부 의도 분류 필요)
            logger.info(f"[IntentRouter] 주간 요약 수락 BUT 플래그 없음 → daily_agent_node")
            detailed_intent = await classify_user_intent(message, llm, user_context, db)
            logger.info(f"[IntentRouter] 세부 의도: {detailed_intent}")
            return "daily_agent_node", UserIntent.DAILY_RECORD.value, detailed_intent

    # 4. 주간 피드백 명시적 요청
    elif intent == "weekly_feedback":
        from datetime import datetime
        from ...config.business_config import WEEKLY_SUMMARY_MIN_WEEKDAY_COUNT

        # temp_data에서 weekday_record_count 및 세션 상태 조회
        temp_data = cached_conv_state.get("temp_data", {}) if cached_conv_state else {}
        qna_session = temp_data.get("weekly_qna_session", {})

        # QnA 세션이 활성화되어 있으면 무조건 weekly_agent_node로 (티키타카 진행 중)
        if qna_session.get("active"):
            logger.info(f"[IntentRouter] QnA 세션 활성 → weekly_agent_node (티키타카 진행)")
            return "weekly_agent_node", UserIntent.WEEKLY_FEEDBACK.value, None

        # 주말 + 평일 작성 일수 체크
        now = datetime.now()
        weekday = now.weekday()  # 0=월, 1=화, ..., 5=토, 6=일
        is_weekend = weekday >= 5

        weekday_count = temp_data.get("weekday_record_count", 0)
        current_week = temp_data.get("weekday_count_week")
        weekly_completed_week = temp_data.get("weekly_completed_week")

        # 주말 체크 (주간요약은 주말에만 가능)
        if not is_weekend:
            logger.info(f"[IntentRouter] 주간 피드백 요청 BUT 평일 → daily_agent_node (주말에만 가능 안내)")
            detailed_intent = "weekly_weekday_only"
            return "daily_agent_node", UserIntent.DAILY_RECORD.value, detailed_intent

        # 평일 작성이 없으면 안내
        if weekday_count == 0:
            logger.info(f"[IntentRouter] 주간 피드백 요청 BUT 평일 작성 없음 → daily_agent_node (안내 메시지)")
            detailed_intent = "weekly_no_record"
            return "daily_agent_node", UserIntent.DAILY_RECORD.value, detailed_intent

        # 평일 작성 부족 시 안내
        if weekday_count < WEEKLY_SUMMARY_MIN_WEEKDAY_COUNT:
            logger.info(f"[IntentRouter] 주간 피드백 요청 BUT 평일 작성 부족 ({weekday_count}일) → daily_agent_node (안내 메시지)")
            detailed_intent = "weekly_insufficient"
            return "daily_agent_node", UserIntent.DAILY_RECORD.value, detailed_intent

        # 이미 완료했는지 체크
        already_completed_this_week = (weekly_completed_week == current_week) if weekly_completed_week else False
        if already_completed_this_week:
            logger.info(f"[IntentRouter] 주간 피드백 요청 BUT 이미 완료 (week={current_week}) → daily_agent_node")
            detailed_intent = "weekly_already_completed"
            return "daily_agent_node", UserIntent.DAILY_RECORD.value, detailed_intent

        # 모든 조건 충족 → 주간요약 v1.0 생성 시작
        logger.info(f"[IntentRouter] ✅ 주간 피드백 조건 충족 → weekly_agent_node (평일 {weekday_count}일, 주말={is_weekend})")
        return "weekly_agent_node", UserIntent.WEEKLY_FEEDBACK.value, None

    # 5. 일일 기록 (기본값)
    else:
        logger.info(f"[IntentRouter] 일일 기록 → daily_agent_node")

        # 세부 의도 분류 (summary/edit_summary/rejection/continue/restart)
        detailed_intent = await classify_user_intent(message, llm, user_context, db)
        logger.info(f"[IntentRouter] 세부 의도: {detailed_intent}")

        return "daily_agent_node", UserIntent.DAILY_RECORD.value, detailed_intent
