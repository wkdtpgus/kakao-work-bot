"""주간요약 역질문 생성 모듈"""
import logging
import json
from typing import List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class FollowUpQuestionsOutput:
    """역질문 생성 결과"""
    questions: List[str]


async def generate_follow_up_questions(
    weekly_summary: str,
    llm
) -> FollowUpQuestionsOutput:
    """주간요약 기반 역질문 생성

    Args:
        weekly_summary: 주간요약 v1.0 텍스트
        llm: LLM 인스턴스

    Returns:
        FollowUpQuestionsOutput: 역질문 리스트 (3개)
    """
    from langchain_core.messages import SystemMessage, HumanMessage
    from ...prompt.weekly_summary_prompt import WEEKLY_FOLLOW_UP_QUESTIONS_PROMPT

    # Structured Output 사용
    try:
        structured_llm = llm.with_structured_output(FollowUpQuestionsOutput)

        messages = [
            SystemMessage(content=WEEKLY_FOLLOW_UP_QUESTIONS_PROMPT),
            HumanMessage(content=f"Weekly Summary:\n{weekly_summary}")
        ]

        result = await structured_llm.ainvoke(messages)

        if not result.questions or len(result.questions) != 3:
            logger.warning(f"[FollowUp] Invalid question count: {len(result.questions) if result.questions else 0}")
            raise ValueError("Invalid question count")

        logger.info(f"[FollowUp] 역질문 생성 완료: {len(result.questions)}개")
        return result

    except Exception as e:
        logger.error(f"[FollowUp] 역질문 생성 실패: {e}")
        # Fallback: 기본 역질문
        return FollowUpQuestionsOutput(questions=[
            "이번 주 가장 의미 있었던 성과는 무엇인가요?",
            "어떤 어려움이 있었고 어떻게 해결하셨나요?",
            "다음 주에 집중하고 싶은 목표는 무엇인가요?"
        ])
