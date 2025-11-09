"""온보딩 정보 추출 서비스 (LLM 호출만)"""
from ...chatbot.state import ExtractionResponse, OnboardingIntent
from langchain_core.messages import SystemMessage, HumanMessage
import logging

logger = logging.getLogger(__name__)


async def extract_field_value(
    message: str,
    target_field: str,
    history_text: str = ""
) -> ExtractionResponse:
    """사용자 메시지에서 특정 필드 값을 LLM으로 추출

    Args:
        message: 사용자 메시지
        target_field: 현재 수집 중인 필드명
        history_text: 포맷팅된 대화 히스토리 (선택)

    Returns:
        ExtractionResponse: LLM 추출 결과
    """
    from ...prompt.onboarding import (
        EXTRACTION_SYSTEM_PROMPT,
        EXTRACTION_USER_PROMPT_TEMPLATE,
        FIELD_DESCRIPTIONS
    )
    from ...utils.models import get_onboarding_llm

    # ========================================
    # 1. 추출 프롬프트 구성
    # ========================================
    field_description = FIELD_DESCRIPTIONS.get(target_field, "")
    extraction_prompt = EXTRACTION_USER_PROMPT_TEMPLATE.format(
        target_field=target_field,
        field_description=field_description,
        user_message=message[:300]  # 최대 300자
    )

    # 대화 히스토리를 포함한 전체 프롬프트
    full_prompt = f"""**대화 컨텍스트:**
{history_text if history_text else "(첫 메시지)"}

{extraction_prompt}"""

    # ========================================
    # 2. LLM 호출 (structured output)
    # ========================================
    base_llm = get_onboarding_llm()
    extraction_llm = base_llm.with_structured_output(ExtractionResponse)

    logger.info(f"[ExtractionService] LLM 호출 시작 (target_field={target_field})")
    logger.debug(f"[ExtractionService] 프롬프트:\n{full_prompt[:500]}...")

    extraction_result = await extraction_llm.ainvoke([
        SystemMessage(content=EXTRACTION_SYSTEM_PROMPT),
        HumanMessage(content=full_prompt)
    ])

    logger.debug(f"[ExtractionService] LLM 응답 타입: {type(extraction_result)}")

    # None 체크 및 기본값 처리
    if extraction_result is None:
        logger.warning(f"[ExtractionService] LLM이 None 반환 - 기본 INVALID 응답 생성")
        extraction_result = ExtractionResponse(
            intent=OnboardingIntent.INVALID,
            extracted_value=None,
            confidence=0.0
        )
    else:
        logger.info(
            f"[ExtractionService] 추출 완료 - "
            f"intent={extraction_result.intent}, "
            f"value={extraction_result.extracted_value}, "
            f"confidence={extraction_result.confidence}"
        )

    return extraction_result
