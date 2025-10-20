"""주간 피드백 생성 서비스 (순수 LLM 호출만)

DB 접근 로직 없음 - Repository에서 준비한 데이터를 받아서 LLM 호출만 수행
"""
from langchain_core.messages import SystemMessage, HumanMessage
from ..prompt.weekly_summary_prompt import WEEKLY_AGENT_SYSTEM_PROMPT
from .schemas import WeeklyFeedbackInput, WeeklyFeedbackOutput
from langsmith import traceable
import logging

logger = logging.getLogger(__name__)


@traceable(name="generate_weekly_feedback")
async def generate_weekly_feedback(
    input_data: WeeklyFeedbackInput,
    llm
) -> WeeklyFeedbackOutput:
    """주간 피드백 생성 (순수 LLM 호출)

    Args:
        input_data: Repository에서 준비한 입력 데이터 (WeeklyFeedbackInput)
        llm: LLM 인스턴스

    Returns:
        WeeklyFeedbackOutput: LLM이 생성한 주간 피드백 결과
    """
    try:
        logger.info(f"[WeeklyFeedback] 주간 피드백 생성 시작")

        # 주간 피드백 프롬프트 구성
        system_prompt = WEEKLY_AGENT_SYSTEM_PROMPT.format(
            name=input_data.user_metadata.name,
            job_title=input_data.user_metadata.job_title,
            career_goal=input_data.user_metadata.career_goal,
            summary=input_data.formatted_context
        )

        # LLM 호출
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content="위 대화 내용을 바탕으로 주간 피드백을 작성해주세요.")
        ])

        weekly_feedback = response.content.strip()
        logger.info(f"[WeeklyFeedback] 주간 피드백 생성 완료 (길이: {len(weekly_feedback)}자)")

        return WeeklyFeedbackOutput(
            feedback_text=weekly_feedback
        )

    except Exception as e:
        logger.error(f"[WeeklyFeedback] 주간 피드백 생성 실패: {e}")
        raise
