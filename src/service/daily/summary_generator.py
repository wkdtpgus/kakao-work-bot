"""일일 요약 생성 서비스 (순수 LLM 호출만)

DB 접근 로직 없음 - Repository에서 준비한 데이터를 받아서 LLM 호출만 수행
"""
from langchain_core.messages import SystemMessage, HumanMessage
from ...prompt.daily_summary_prompt import DAILY_SUMMARY_SYSTEM_PROMPT, DAILY_SUMMARY_USER_PROMPT
from ...utils.schemas import DailySummaryInput, DailySummaryOutput
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

        # 시스템 프롬프트 구성 (수정 요청이 있으면 명시적으로 주입)
        system_prompt = DAILY_SUMMARY_SYSTEM_PROMPT
        if input_data.user_correction:
            correction_instruction = f"""

# USER CORRECTION REQUEST
The user requested the following changes:
"{input_data.user_correction}"

CRITICAL RULES for corrections:
- ONLY use information from the conversation_turns provided in the USER_DATA section
- If the user denied something (e.g., "안했어", "그거 아니야"), COMPLETELY remove that topic
- If the user requested to ADD something, search ONLY in today's conversation_turns for that content
- If the requested content exists in today's conversation, add it to the summary
- If the requested content does NOT appear anywhere in today's conversation_turns, respond: "죄송합니다. 오늘 대화에서 해당 내용을 찾을 수 없습니다. 오늘 대화하신 내용만 요약에 포함할 수 있어요."
- DO NOT use information from previous days or your general knowledge
- ONLY summarize what the user explicitly said in today's conversation

CRITICAL: Even after corrections, you MUST NOT use Markdown syntax
- Use plain text only
- NO bold, markdown, italics, headers, or bullet points"""
            system_prompt = system_prompt + correction_instruction

        # LLM 호출
        summary_response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
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
