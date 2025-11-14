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

logger = logging.getLogger(__name__)


def classify_service_intent_rule_based(
    message: str,
    cached_conv_state: Optional[dict] = None
) -> Tuple[str, bool]:
    """
    규칙 기반 서비스 의도 분류 (LLM 제거 - 성능 최적화)

    Args:
        message: 사용자 메시지 (맥락 포함 가능)
        cached_conv_state: 캐시된 conversation_state (weekly 플래그 체크용)

    Returns:
        (intent, has_weekly_flag)
        - intent: "daily_record" | "weekly_feedback" | "weekly_acceptance" | "rejection"
        - has_weekly_flag: 주간 요약 플래그 존재 여부
    """
    # ===== 플래그/상태 기반 우선 라우팅 =====
    has_weekly_flag = False
    if cached_conv_state:
        temp_data = cached_conv_state.get("temp_data", {})
        current_step = cached_conv_state.get("current_step", "")
        has_weekly_flag = (
            temp_data.get("weekly_summary_ready", False) or
            current_step == "weekly_summary_pending"
        )

    message_lower = message.lower().strip()

    # ===== 규칙 기반 분류 =====

    # 1. 플래그 있을 때: 주간 요약 제안에 대한 응답 분류
    if has_weekly_flag:
        # 거절 키워드 (우선순위 높음)
        rejection_keywords = ["아니", "싫어", "나중에", "안 할래", "됐어", "거절", "no", "아뇨", "안돼", "싫"]
        if any(keyword in message_lower for keyword in rejection_keywords):
            logger.info(f"[IntentRouter] 규칙 기반: 거절 키워드 감지 → rejection")
            return "rejection", has_weekly_flag

        # 수락 키워드
        acceptance_keywords = ["응", "네", "좋아", "그래", "보여줘", "볼래", "okay", "yes", "ㅇㅇ", "ㄱㄱ", "알겠어", "부탁"]
        if any(keyword in message_lower for keyword in acceptance_keywords):
            logger.info(f"[IntentRouter] 규칙 기반: 수락 키워드 감지 → weekly_acceptance")
            return "weekly_acceptance", has_weekly_flag

        # 명확하지 않으면 daily_record (사용자가 다른 주제로 전환)
        logger.info(f"[IntentRouter] 규칙 기반: 플래그 있으나 명확한 응답 없음 → daily_record")
        return "daily_record", has_weekly_flag

    # 2. 플래그 없을 때: 주간요약 요청 키워드 체크
    weekly_keywords = ["주간요약", "주간 요약", "주간피드백", "주간 피드백", "위클리", "weekly"]
    if any(keyword in message_lower for keyword in weekly_keywords):
        logger.info(f"[IntentRouter] 규칙 기반: 주간요약 키워드 감지 → weekly_feedback")
        return "weekly_feedback", has_weekly_flag

    # 3. 기본값: daily_record
    logger.info(f"[IntentRouter] 규칙 기반: 기본값 → daily_record")
    return "daily_record", has_weekly_flag


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

    # 0. 🔥 최우선 체크: 주간 QnA 세션 활성화 여부 OR 주간 완료 후 반복 접근
    if cached_conv_state:
        temp_data = cached_conv_state.get("temp_data", {})
        qna_session = temp_data.get("weekly_qna_session", {})

        # 티키타카 진행 중
        if qna_session.get("active"):
            logger.info(f"[IntentRouter] 🔥 QnA 세션 활성 감지 → weekly_agent_node (최우선 라우팅)")
            return "weekly_agent_node", UserIntent.WEEKLY_FEEDBACK.value, None

        # v2.0 완료 후 반복 접근 체크 (이번 주 완료했으면 weekly로 라우팅하여 마무리 멘트 출력)
        from datetime import datetime
        now = datetime.now()
        current_week = now.isocalendar()[1]
        weekly_completed_week = temp_data.get("weekly_completed_week")

        if weekly_completed_week == current_week:
            logger.info(f"[IntentRouter] 🔥 주간 완료 후 반복 접근 감지 → weekly_agent_node (마무리 멘트)")
            return "weekly_agent_node", UserIntent.WEEKLY_FEEDBACK.value, None

    # 1. 최상위 의도 분류 (규칙 기반 - LLM 제거)
    intent, has_weekly_flag = classify_service_intent_rule_based(message, cached_conv_state)

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

        # temp_data 조회
        temp_data = cached_conv_state.get("temp_data", {}) if cached_conv_state else {}

        # 주말 + 평일 작성 일수 체크
        now = datetime.now()
        weekday = now.weekday()  # 0=월, 1=화, ..., 5=토, 6=일
        is_weekend = weekday >= 5

        # 이번 주 평일 기록 수를 DB에서 동적으로 계산
        from ...database.summary_repository import count_this_week_weekday_records
        weekday_count = await count_this_week_weekday_records(db, user_context.user_id)

        # ISO 주차 번호 계산 (current_week)
        current_week = now.isocalendar()[1]  # ISO 주차 (1-53)
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
