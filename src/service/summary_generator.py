"""일일 요약 생성 서비스"""
from langchain_core.messages import SystemMessage, HumanMessage
from ..prompt.daily_summary_prompt import DAILY_SUMMARY_SYSTEM_PROMPT, DAILY_SUMMARY_USER_PROMPT
from langsmith import traceable
import logging

logger = logging.getLogger(__name__)


@traceable(name="generate_daily_summary")
async def generate_daily_summary(
    user_id: str,
    metadata,
    conversation_context: dict,
    llm,
    db
) -> tuple[str, int]:
    """일일 요약 생성 및 출석 카운트 반환

    Args:
        user_id: 사용자 ID
        metadata: 사용자 메타데이터
        conversation_context: 대화 컨텍스트
        llm: LLM 인스턴스
        db: 데이터베이스 인스턴스

    Returns:
        tuple[str, int]: (요약 텍스트, 출석 카운트)
    """
    # 대화 텍스트 구성 (최신 10개, 최신순으로 정렬되어 있으므로 앞에서 10개)
    recent_turns = conversation_context["recent_turns"][:10]
    # 시간순으로 역정렬하여 오래된 대화 → 최신 대화 순서로 표시
    recent_turns_reversed = list(reversed(recent_turns))

    conversation_text = "\n".join([
        f"{'사용자' if t['role'] == 'user' else '봇'}: {t['content']}"
        for t in recent_turns_reversed
    ])

    # 사용자 메타데이터 텍스트
    user_metadata_text = f"""
- 이름: {metadata.name}
- 직무: {metadata.job_title}
- 프로젝트: {metadata.project_name}
- 커리어 목표: {metadata.career_goal}
"""

    # 요약 프롬프트
    summary_prompt = DAILY_SUMMARY_USER_PROMPT.format(
        user_metadata=user_metadata_text,
        conversation_turns=conversation_text
    )

    # LLM 호출
    summary_response = await llm.ainvoke([
        SystemMessage(content=DAILY_SUMMARY_SYSTEM_PROMPT),
        HumanMessage(content=summary_prompt)
    ])

    summary_text = summary_response.content

    # 현재 출석 카운트 조회 (증가는 daily_agent_node에서 처리)
    user = await db.get_user(user_id)
    daily_count = user.get("attendance_count", 0)
    daily_record_count = user.get("daily_record_count", 0)

    logger.info(f"[DailySummary] 요약 생성 완료 (attendance_count={daily_count}일차, daily_record_count={daily_record_count}회)")

    # 일일 기록 DB 저장 (같은 날짜 있으면 최신 내용으로 업데이트)
    from datetime import datetime
    today = datetime.now().date().isoformat()

    await db.save_daily_record(
        user_id=user_id,
        summary_content=summary_text
    )
    logger.info(f"[DailySummary] 일일기록 DB 저장 완료 (record_date: {today})")

    return summary_text, daily_count
