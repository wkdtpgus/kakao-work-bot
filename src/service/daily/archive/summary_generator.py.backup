"""일일 요약 생성 서비스 (순수 LLM 호출만)

DB 접근 로직 없음 - Repository에서 준비한 데이터를 받아서 LLM 호출만 수행
"""
from langchain_core.messages import SystemMessage, HumanMessage
from ...prompt.daily_summary_prompt import (
    DAILY_SUMMARY_SYSTEM_PROMPT,
    DAILY_SUMMARY_USER_PROMPT,
    DAILY_SUMMARY_EDIT_SYSTEM_PROMPT,
    DAILY_SUMMARY_EDIT_USER_PROMPT
)
from ...utils.schemas import DailySummaryInput, DailySummaryOutput
from langsmith import traceable
import logging

logger = logging.getLogger(__name__)


@traceable(name="generate_daily_summary")
async def generate_daily_summary(
    input_data: DailySummaryInput,
    llm
) -> DailySummaryOutput:
    """일일 요약 생성 또는 수정 (순수 LLM 호출)

    Args:
        input_data: Repository에서 준비한 입력 데이터 (DailySummaryInput)
        llm: LLM 인스턴스

    Returns:
        DailySummaryOutput: LLM이 생성한 요약 결과
    """
    try:
        # 🔍 디버깅 로그 추가
        logger.info(f"[DailySummary] 🔍 latest_summary 존재 여부: {input_data.latest_summary is not None}")
        logger.info(f"[DailySummary] 🔍 latest_summary 길이: {len(input_data.latest_summary) if input_data.latest_summary else 0}")
        logger.info(f"[DailySummary] 🔍 user_correction: {input_data.user_correction[:50] if input_data.user_correction else 'None'}")

        # ===== 수정 모드 (latest_summary 존재) =====
        if input_data.latest_summary:
            logger.info("[DailySummary] ✅ 수정 모드 - 최신 요약 기반 수정")

            # 수정 전용 프롬프트 사용
            system_prompt = DAILY_SUMMARY_EDIT_SYSTEM_PROMPT
            user_prompt = DAILY_SUMMARY_EDIT_USER_PROMPT.format(
                user_correction=input_data.user_correction or "",
                existing_summary=input_data.latest_summary
            )

        # ===== 생성 모드 (latest_summary 없음) =====
        else:
            logger.info("[DailySummary] 생성 모드 - 전체 대화 기반 요약")

            # 사용자 메타데이터 텍스트 구성
            user_metadata_text = f"""
- 이름: {input_data.user_metadata.name}
- 직무: {input_data.user_metadata.job_title}
- 프로젝트: {input_data.user_metadata.project_name}
- 커리어 목표: {input_data.user_metadata.career_goal}
"""

            # 생성 전용 프롬프트 사용
            system_prompt = DAILY_SUMMARY_SYSTEM_PROMPT
            user_prompt = DAILY_SUMMARY_USER_PROMPT.format(
                user_metadata=user_metadata_text,
                conversation_turns=input_data.conversation_context
            )

        # LLM 호출
        summary_response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ])

        summary_text = summary_response.content

        mode = "수정" if input_data.latest_summary else "생성"
        logger.info(
            f"[DailySummary] 요약 {mode} 완료 "
            f"(attendance_count={input_data.attendance_count}일차, "
            f"daily_record_count={input_data.daily_record_count}회)"
        )

        return DailySummaryOutput(
            summary_text=summary_text
        )

    except Exception as e:
        logger.error(f"[DailySummary] 요약 생성/수정 실패: {e}")
        raise
