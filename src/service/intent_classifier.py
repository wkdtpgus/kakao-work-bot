"""사용자 의도 분류 서비스"""
from langchain_core.messages import SystemMessage, HumanMessage
from ..prompt.intent_classifier import INTENT_CLASSIFICATION_SYSTEM_PROMPT, INTENT_CLASSIFICATION_USER_PROMPT
from langsmith import traceable


@traceable(name="classify_user_intent")
async def classify_user_intent(message: str, llm) -> str:
    """사용자 의도 분류 (summary/continue/restart)

    Args:
        message: 사용자 메시지
        llm: LLM 인스턴스

    Returns:
        str: "summary", "continue", "restart" 중 하나
    """
    intent_response = await llm.ainvoke([
        SystemMessage(content=INTENT_CLASSIFICATION_SYSTEM_PROMPT),
        HumanMessage(content=INTENT_CLASSIFICATION_USER_PROMPT.format(message=message))
    ])

    return intent_response.content.strip().lower()
