"""주간 피드백 생성 서비스"""
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from ..prompt.weekly_summary_prompt import WEEKLY_AGENT_SYSTEM_PROMPT
from ..utils.models import CHAT_MODEL_CONFIG
from langsmith import traceable
import logging
import os

logger = logging.getLogger(__name__)


@traceable(name="generate_weekly_feedback")
async def generate_weekly_feedback(user_id: str, db) -> str:
    """주간 피드백 생성

    Args:
        user_id: 사용자 ID
        db: Database 인스턴스

    Returns:
        str: 주간 피드백 텍스트
    """
    try:
        logger.info(f"[WeeklyFeedback] 주간 피드백 생성 시작: {user_id}")

        # 1. 사용자 정보 조회
        user = await db.get_user(user_id)
        if not user:
            logger.warning(f"[WeeklyFeedback] 사용자 정보 없음: {user_id}")
            return "사용자 정보를 찾을 수 없습니다."

        name = user.name or "사용자"
        job_title = user.job_title or "직무 정보 없음"
        career_goal = user.career_goal or "목표 정보 없음"

        # 2. 최근 7개 데일리 요약 조회 (ai_answer_messages, summary_type='daily')
        daily_summaries = await db.get_daily_summaries_v2(user_id, limit=7)

        if not daily_summaries or len(daily_summaries) == 0:
            logger.warning(f"[WeeklyFeedback] 데일리 요약 없음 → 최근 대화 히스토리로 대체")

            # 최근 대화 히스토리로 fallback (V2 스키마 사용)
            recent_turns = await db.get_recent_turns_v2(user_id, limit=20)

            formatted_messages = []
            for turn in recent_turns:
                formatted_messages.append(f"사용자: {turn.get('user_message', '')}")
                formatted_messages.append(f"AI: {turn.get('ai_message', '')}")

            full_context = "[최근 대화]\n" + "\n".join(formatted_messages)
        else:
            # 데일리 요약 기반 컨텍스트 구성
            formatted_summaries = []
            for summary in reversed(daily_summaries):  # 오래된 순으로 정렬
                session_date = summary.get("session_date", "날짜 미상")
                content = summary.get("summary_content", "")
                formatted_summaries.append(f"**{session_date}**\n{content}")

            full_context = "\n\n".join(formatted_summaries)
            logger.info(f"[WeeklyFeedback] 데일리 요약 기반 컨텍스트 구성 완료 ({len(daily_summaries)}개)")

        # 4. 주간 피드백 프롬프트 구성
        system_prompt = WEEKLY_AGENT_SYSTEM_PROMPT.format(
            name=name,
            job_title=job_title,
            career_goal=career_goal,
            summary=full_context
        )

        # 5. LLM 호출
        llm = ChatOpenAI(**CHAT_MODEL_CONFIG, api_key=os.getenv("OPENAI_API_KEY"))

        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content="위 대화 내용을 바탕으로 주간 피드백을 작성해주세요.")
        ])

        weekly_feedback = response.content.strip()
        logger.info(f"[WeeklyFeedback] 주간 피드백 생성 완료 (길이: {len(weekly_feedback)}자)")

        return weekly_feedback

    except Exception as e:
        logger.error(f"[WeeklyFeedback] 주간 피드백 생성 실패: {e}")
        import traceback
        traceback.print_exc()
        return "주간 피드백 생성 중 오류가 발생했습니다."
