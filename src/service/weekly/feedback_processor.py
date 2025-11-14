"""주간 피드백 처리 비즈니스 로직 (Weekly Agent용)"""
import logging
from typing import Tuple, Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class WeeklyFeedbackResponse:
    """주간 피드백 처리 결과"""
    ai_response: str
    is_summary: bool = False
    summary_type: Optional[str] = None
    should_clear_flag: bool = False  # 정식 주간요약 생성 후 플래그 정리 필요 여부


# handle_official_weekly_feedback, handle_no_record_yet, handle_partial_weekly_feedback 제거됨
# 이제 weekly_v1 → weekly_qna → weekly_v2 플로우만 사용


async def handle_weekly_v1_request(
    db,
    user_id: str,
    metadata,
    llm
) -> WeeklyFeedbackResponse:
    """주간요약 v1.0 + 역질문 생성 (사용자 요청 시)

    Args:
        db: Database 인스턴스
        user_id: 사용자 ID
        metadata: UserMetadata 객체
        llm: LLM 인스턴스

    Returns:
        WeeklyFeedbackResponse: v1.0 + 역질문
    """
    from ...database import prepare_weekly_feedback_data
    from .feedback_generator import generate_weekly_feedback
    from .follow_up_generator import generate_follow_up_questions

    logger.info(f"[WeeklyV1] 주간요약 v1.0 생성 시작")

    # v1.0 생성
    user_data = {
        "name": metadata.name,
        "job_title": metadata.job_title,
        "career_goal": metadata.career_goal
    }

    input_data = await prepare_weekly_feedback_data(db, user_id, user_data=user_data)
    v1_output = await generate_weekly_feedback(input_data, llm)

    # 역질문 생성
    follow_up_output = await generate_follow_up_questions(v1_output.feedback_text, llm)

    # temp_data에 저장 (v2.0 생성 시 필요)
    conv_state = await db.get_conversation_state(user_id)
    temp_data = conv_state.get("temp_data", {}) if conv_state else {}

    temp_data["weekly_qna_session"] = {
        "active": True,
        "v1_summary": v1_output.feedback_text,
        "follow_up_questions": follow_up_output.questions,
        "turn_count": 0,
        "max_turns": 5,
        "conversation_history": []
    }

    # current_step 유지
    current_step = conv_state.get("current_step", "weekly_qna") if conv_state else "weekly_qna"
    await db.upsert_conversation_state(user_id, current_step=current_step, temp_data=temp_data)

    # 응답 포맷팅
    response = f"{v1_output.feedback_text}\n\n💬 궁금한 점이 있어요:\n"
    for i, q in enumerate(follow_up_output.questions, 1):
        response += f"{i}. {q}\n"

    logger.info(f"[WeeklyV1] v1.0 + 역질문 제공 완료")

    return WeeklyFeedbackResponse(
        ai_response=response,
        is_summary=True,
        summary_type='weekly_v1'
    )


async def handle_weekly_qna_response(
    db,
    user_id: str,
    message: str,
    llm
) -> WeeklyFeedbackResponse:
    """역질문 티키타카 처리 (최대 5회)

    Args:
        db: Database 인스턴스
        user_id: 사용자 ID
        message: 사용자 메시지
        llm: LLM 인스턴스

    Returns:
        WeeklyFeedbackResponse: 티키타카 응답 or v2.0
    """
    from langchain_core.messages import SystemMessage, HumanMessage

    # 세션 조회
    conv_state = await db.get_conversation_state(user_id)
    temp_data = conv_state.get("temp_data", {}) if conv_state else {}
    session = temp_data.get("weekly_qna_session")

    if not session or not session.get("active"):
        return WeeklyFeedbackResponse(
            ai_response="세션이 만료되었어요. 다시 주간요약을 요청해주세요."
        )

    # 대화 히스토리 저장
    session["conversation_history"].append({"user": message})
    session["turn_count"] += 1

    # 5회 달성 → v2.0 생성
    if session["turn_count"] >= session["max_turns"]:
        return await generate_weekly_v2(db, user_id, session, llm)

    # 자연스러운 후속 질문 생성
    from ...prompt.weekly_summary_prompt import (
        WEEKLY_TIKITAKA_QUESTION_PROMPT,
        WEEKLY_TIKITAKA_FINAL_QUESTION_PROMPT
    )

    # 5번째 턴(마지막 질문) → 대화 마무리 + 소감 요청
    is_final_turn = (session["turn_count"] == session["max_turns"])
    system_prompt = WEEKLY_TIKITAKA_FINAL_QUESTION_PROMPT if is_final_turn else WEEKLY_TIKITAKA_QUESTION_PROMPT

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"사용자 답변: {message}")
    ]

    response = await llm.ainvoke(messages)
    follow_up = response.content

    session["conversation_history"][-1]["ai"] = follow_up

    # 세션 업데이트
    temp_data["weekly_qna_session"] = session
    # current_step 유지
    conv_state = await db.get_conversation_state(user_id)
    current_step = conv_state.get("current_step", "weekly_qna") if conv_state else "weekly_qna"
    await db.upsert_conversation_state(user_id, current_step=current_step, temp_data=temp_data)

    logger.info(f"[WeeklyQnA] 티키타카 진행 중: {session['turn_count']}/{session['max_turns']}")

    return WeeklyFeedbackResponse(ai_response=follow_up)


async def generate_weekly_v2(
    db,
    user_id: str,
    session: dict,
    llm
) -> WeeklyFeedbackResponse:
    """주간요약 v2.0 생성 (QnA 완료 후)

    Args:
        db: Database 인스턴스
        user_id: 사용자 ID
        session: QnA 세션 데이터
        llm: LLM 인스턴스

    Returns:
        WeeklyFeedbackResponse: v2.0
    """
    from langchain_core.messages import SystemMessage, HumanMessage
    from ...prompt.weekly_summary_prompt import WEEKLY_V2_GENERATION_PROMPT

    logger.info(f"[WeeklyV2] 주간요약 v2.0 생성 시작")

    # v1.0 + QnA 히스토리 포맷팅
    v1_summary = session["v1_summary"]
    qna_history = session["conversation_history"]

    qna_text = "\n\n".join([
        f"Q: {turn.get('ai', '')}\nA: {turn.get('user', '')}"
        for turn in qna_history
        if turn.get('ai') and turn.get('user')
    ])

    messages = [
        SystemMessage(content=WEEKLY_V2_GENERATION_PROMPT),
        HumanMessage(content=f"# v1.0 요약\n{v1_summary}\n\n# 추가 대화\n{qna_text}")
    ]

    response = await llm.ainvoke(messages)
    v2_summary = response.content

    # v2.0 저장
    await db.save_conversation_turn(
        user_id,
        user_message="주간요약 v2.0 생성",
        ai_message=v2_summary,
        is_summary=True,
        summary_type='weekly_v2'
    )

    # 세션 종료 + weekly_completed_week 설정 (중복 방지)
    from ...config import get_kst_now

    session["active"] = False
    conv_state = await db.get_conversation_state(user_id)
    temp_data = conv_state.get("temp_data", {}) if conv_state else {}
    temp_data["weekly_qna_session"] = session

    # 이번 주 완료 표시 (ISO 주차 번호 사용, 한국 시간 기준)
    now = get_kst_now()
    current_week = now.isocalendar()[1]  # ISO 주차 (1-53)
    temp_data["weekly_completed_week"] = current_week

    # current_step 유지
    current_step = conv_state.get("current_step", "weekly_completed") if conv_state else "weekly_completed"
    await db.upsert_conversation_state(user_id, current_step=current_step, temp_data=temp_data)

    logger.info(f"[WeeklyV2] v2.0 생성 완료, 세션 종료")

    return WeeklyFeedbackResponse(
        ai_response=f"{v2_summary}\n\n수고하셨어요! 다음 주에도 열심히 기록해봐요! 😊",
        is_summary=True,
        summary_type='weekly_v2'
    )


# process_weekly_feedback 제거됨 - weekly_agent_node에서 세션 기반 분기로 대체
# 이제 weekly_v1 → weekly_qna → weekly_v2 플로우만 사용
