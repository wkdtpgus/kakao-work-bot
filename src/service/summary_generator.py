"""일일 요약 생성 서비스 (순수 LLM 호출만)

DB 접근 로직 없음 - Repository에서 준비한 데이터를 받아서 LLM 호출만 수행
"""
from langchain_core.messages import SystemMessage, HumanMessage
from ..prompt.daily_summary_prompt import DAILY_SUMMARY_SYSTEM_PROMPT, DAILY_SUMMARY_USER_PROMPT
from .schemas import DailySummaryInput, DailySummaryOutput
from langsmith import traceable
import logging

logger = logging.getLogger(__name__)


@traceable(name="generate_daily_summary")
async def generate_daily_summary(
    input_data: DailySummaryInput,
    llm
) -> DailySummaryOutput:
    """일일 요약 생성 (순수 LLM 호출)

    Args:
        input_data: Repository에서 준비한 입력 데이터 (DailySummaryInput)
        llm: LLM 인스턴스

    Returns:
        DailySummaryOutput: LLM이 생성한 요약 결과
    """
    try:
        # 사용자 메타데이터 텍스트 구성
        user_metadata_text = f"""
- 이름: {input_data.user_metadata.name}
- 직무: {input_data.user_metadata.job_title}
- 프로젝트: {input_data.user_metadata.project_name}
- 커리어 목표: {input_data.user_metadata.career_goal}
"""

        # 요약 프롬프트 구성
        summary_prompt = DAILY_SUMMARY_USER_PROMPT.format(
            user_metadata=user_metadata_text,
            conversation_turns=input_data.conversation_context
        )

        # LLM 호출
        summary_response = await llm.ainvoke([
            SystemMessage(content=DAILY_SUMMARY_SYSTEM_PROMPT),
            HumanMessage(content=summary_prompt)
        ])

        summary_text = summary_response.content

        logger.info(
            f"[DailySummary] 요약 생성 완료 "
            f"(attendance_count={input_data.attendance_count}일차, "
            f"daily_record_count={input_data.daily_record_count}회)"
        )

        return DailySummaryOutput(
            summary_text=summary_text
        )

    except Exception as e:
        logger.error(f"[DailySummary] 요약 생성 실패: {e}")
        raise
