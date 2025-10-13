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
async def generate_weekly_feedback(user_id: str, db, memory_manager) -> str:
    """주간 피드백 생성

    Args:
        user_id: 사용자 ID
        db: Database 인스턴스
        memory_manager: MemoryManager 인스턴스

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

        name = user.get("name", "사용자")
        job_title = user.get("job_title", "직무 정보 없음")
        career_goal = user.get("career_goal", "목표 정보 없음")

        # 2. 최근 7일치 일일 기록 조회
        daily_records = await db.get_daily_records(user_id, limit=7)

        if not daily_records or len(daily_records) == 0:
            logger.warning(f"[WeeklyFeedback] 일일 기록 없음 → 대화 히스토리로 대체")

            # 대화 히스토리로 fallback (기존 로직)
            conversation_context = await memory_manager.get_contextualized_history(user_id, db)
            summary = conversation_context.get("summary", "")
            recent_turns = conversation_context.get("recent_turns", [])

            formatted_messages = []
            for msg in recent_turns:
                role = "사용자" if msg.get("role") == "user" else "AI"
                content = msg.get("content", "")
                formatted_messages.append(f"{role}: {content}")

            recent_conversation = "\n".join(formatted_messages)

            if summary:
                full_context = f"[이전 대화 요약]\n{summary}\n\n[최근 대화]\n{recent_conversation}"
            else:
                full_context = f"[최근 대화]\n{recent_conversation}"
        else:
            # 일일 기록 기반 컨텍스트 구성
            formatted_records = []
            for record in reversed(daily_records):  # 오래된 순으로 정렬
                record_date = record.get("record_date", "날짜 미상")
                work_content = record.get("work_content", "")
                formatted_records.append(f"**{record_date}**\n{work_content}")

            full_context = "\n\n".join(formatted_records)
            logger.info(f"[WeeklyFeedback] 일일 기록 기반 컨텍스트 구성 완료 ({len(daily_records)}일치)")

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
