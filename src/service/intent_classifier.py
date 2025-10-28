"""사용자 의도 분류 서비스"""
from langchain_core.messages import SystemMessage, HumanMessage
from ..prompt.intent_classifier import INTENT_CLASSIFICATION_SYSTEM_PROMPT, INTENT_CLASSIFICATION_USER_PROMPT
from langsmith import traceable
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@traceable(name="classify_user_intent")
async def classify_user_intent(message: str, llm, user_context=None, db=None) -> str:
    """사용자 의도 분류 (summary/edit_summary/continue/restart/no_record_today)

    Args:
        message: 사용자 메시지
        llm: LLM 인스턴스
        user_context: 사용자 컨텍스트 (선택)
        db: Database 인스턴스 (선택)

    Returns:
        str: "summary", "edit_summary", "continue", "restart", "no_record_today" 중 하나
    """
    intent_response = await llm.ainvoke([
        SystemMessage(content=INTENT_CLASSIFICATION_SYSTEM_PROMPT),
        HumanMessage(content=INTENT_CLASSIFICATION_USER_PROMPT.format(message=message))
    ])

    intent = intent_response.content.strip().lower()
    logger.info(f"🎯 [IntentClassifier] 사용자 메시지: '{message}' → 분류 결과: '{intent}'")

    # edit_summary 의도는 요약 직후에만 유효 (last_summary_at 플래그 체크)
    if "edit_summary" in intent and user_context:
        last_summary_at = user_context.daily_session_data.get("last_summary_at")
        if not last_summary_at:
            # 요약 생성한 적 없으면 일반 대화로 처리
            logger.info(f"🔄 [IntentClassifier] edit_summary이지만 요약 전 → continue로 변경")
            return "continue"

    # 요약 요청 시 오늘 대화 존재 여부 체크
    if "summary" in intent and user_context:
        # daily_record_count 체크 (날짜 리셋 시에만 0으로 초기화, 당일에는 계속 증가)
        daily_record_count = user_context.daily_record_count

        if daily_record_count == 0:
            # 오늘 대화가 없으면 no_record_today 반환
            logger.info(f"🔄 [IntentClassifier] summary이지만 오늘 대화 없음 → no_record_today로 변경")
            return "no_record_today"

    logger.info(f"✅ [IntentClassifier] 최종 인텐트: '{intent}'")
    return intent
