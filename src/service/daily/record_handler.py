"""일일 기록 처리 비즈니스 로직 (Daily Agent용)"""
import logging
from typing import Tuple, Optional, Dict, Any
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DailyRecordResponse:
    """일일 기록 처리 결과"""
    ai_response: str
    is_summary_response: bool = False
    summary_type: Optional[str] = None
    is_edit_summary: bool = False
    should_update_session: bool = True
    early_return: bool = False  # 7일차 제안 등으로 조기 종료 필요 시 True


async def handle_no_record_today(
    user_context,
    metadata
) -> DailyRecordResponse:
    """오늘 기록 없이 요약 요청한 경우 처리

    Args:
        user_context: UserContext 객체
        metadata: UserMetadata 객체

    Returns:
        DailyRecordResponse: 처리 결과
    """
    from ...utils.utils import reset_session_data

    logger.info(f"[DailyRecordHandler] 오늘 날짜 기록 없이 요약 요청 → 거부")
    reset_session_data(user_context)

    return DailyRecordResponse(
        ai_response=f"{metadata.name}님, 오늘의 일일기록을 먼저 진행해주세요! 오늘 하신 업무에 대해 이야기 나눠볼까요?"
    )


async def handle_rejection(
    user_context,
    metadata
) -> DailyRecordResponse:
    """거절 처리 (요약 제안 거절)

    Args:
        user_context: UserContext 객체
        metadata: UserMetadata 객체

    Returns:
        DailyRecordResponse: 처리 결과
    """
    from ...utils.utils import reset_session_data

    logger.info(f"[DailyRecordHandler] 거절 감지 → 세션 초기화")
    reset_session_data(user_context)

    return DailyRecordResponse(
        ai_response=f"알겠습니다, {metadata.name}님! 다시 시작할 때 편하게 말씀해주세요."
    )


async def handle_end_conversation(
    user_context,
    metadata
) -> DailyRecordResponse:
    """대화 종료 요청 처리

    Args:
        user_context: UserContext 객체
        metadata: UserMetadata 객체

    Returns:
        DailyRecordResponse: 처리 결과
    """
    from ...utils.utils import reset_session_data

    logger.info(f"[DailyRecordHandler] 대화 종료 요청")
    reset_session_data(user_context)

    return DailyRecordResponse(
        ai_response=f"좋아요 {metadata.name}님, 오늘도 수고하셨습니다! 내일 다시 만나요 😊"
    )


async def handle_no_edit_needed(
    user_context,
    metadata
) -> DailyRecordResponse:
    """수정 불필요 처리 (요약 만족)

    Args:
        user_context: UserContext 객체
        metadata: UserMetadata 객체

    Returns:
        DailyRecordResponse: 처리 결과
    """
    from ...utils.utils import reset_session_data

    logger.info(f"[DailyRecordHandler] 수정 불필요 (요약 후) → 깔끔하게 마무리")
    reset_session_data(user_context)

    return DailyRecordResponse(
        ai_response=f"좋아요 {metadata.name}님, 오늘도 수고하셨습니다! 내일 다시 만나요 😊"
    )


async def handle_edit_summary(
    db,
    user_id: str,
    message: str,
    user_context,
    metadata,
    llm
) -> DailyRecordResponse:
    """요약 수정 요청 처리

    Args:
        db: Database 인스턴스
        user_id: 사용자 ID
        message: 사용자 메시지 (수정 요청)
        user_context: UserContext 객체
        metadata: UserMetadata 객체
        llm: LLM 인스턴스

    Returns:
        DailyRecordResponse: 처리 결과
    """
    from ...database import prepare_daily_summary_data
    from .summary_generator import generate_daily_summary

    logger.info(f"[DailyRecordHandler] 요약 수정 요청 → 사용자 피드백 반영")

    # 요약 수정 시 오늘 전체 대화 조회 (기존 버전은 전체 대화 재분석)
    today = datetime.now().date().isoformat()
    all_today_turns = await db.get_conversation_history_by_date_v2(user_id, today, limit=50)
    logger.info(f"[DailyRecordHandler] 수정용 전체 대화 조회: {len(all_today_turns)}턴")

    # user_data 캐시 전달 (중복 DB 쿼리 방지)
    user_data = _build_user_data(metadata, user_context)

    # 요약 재생성 (user_correction과 함께 전체 대화 전달)
    input_data = await prepare_daily_summary_data(
        db,
        user_id,
        all_today_turns,
        user_correction=message,
        user_data=user_data
    )
    output = await generate_daily_summary(input_data, llm)
    ai_response = output.summary_text
    current_attendance_count = input_data.attendance_count

    # last_summary_at 업데이트 + conversation_count 리셋
    user_context.daily_session_data["last_summary_at"] = datetime.now().isoformat()
    user_context.daily_session_data["conversation_count"] = 0
    logger.info(f"[DailyRecordHandler] 요약 수정 완료 → conversation_count 리셋")

    # 7일차 체크
    ai_response_final, weekly_suggested = await check_and_suggest_weekly_summary(
        db, user_id, user_context, current_attendance_count,
        ai_response, message, is_summary=True, summary_type='daily'
    )

    return DailyRecordResponse(
        ai_response=ai_response_final,
        is_summary_response=True,
        summary_type='daily',
        is_edit_summary=True,
        early_return=weekly_suggested
    )


async def handle_summary_request(
    db,
    user_id: str,
    message: str,
    user_context,
    metadata,
    llm
) -> DailyRecordResponse:
    """요약 생성 요청 처리

    Args:
        db: Database 인스턴스
        user_id: 사용자 ID
        message: 사용자 메시지
        user_context: UserContext 객체
        metadata: UserMetadata 객체
        llm: LLM 인스턴스

    Returns:
        DailyRecordResponse: 처리 결과
    """
    from ...database import prepare_daily_summary_data
    from .summary_generator import generate_daily_summary

    logger.info(f"[DailyRecordHandler] 요약 생성 요청")

    # 요약 생성 시 오늘 전체 대화 조회
    today = datetime.now().date().isoformat()
    all_today_turns = await db.get_conversation_history_by_date_v2(user_id, today, limit=50)
    logger.info(f"[DailyRecordHandler] 요약용 전체 대화 조회: {len(all_today_turns)}턴")

    # user_data 캐시 전달 (중복 DB 쿼리 방지)
    user_data = _build_user_data(metadata, user_context)

    # 요약 생성
    input_data = await prepare_daily_summary_data(db, user_id, all_today_turns, user_data=user_data)
    output = await generate_daily_summary(input_data, llm)
    ai_response = output.summary_text
    current_attendance_count = input_data.attendance_count

    # last_summary_at 플래그 저장 + conversation_count 리셋
    user_context.daily_session_data["last_summary_at"] = datetime.now().isoformat()
    user_context.daily_session_data["conversation_count"] = 0
    logger.info(f"[DailyRecordHandler] 요약 생성 완료 → conversation_count 리셋")

    # 7일차 체크
    ai_response_final, weekly_suggested = await check_and_suggest_weekly_summary(
        db, user_id, user_context, current_attendance_count,
        ai_response, message, is_summary=True, summary_type='daily'
    )

    return DailyRecordResponse(
        ai_response=ai_response_final,
        is_summary_response=True,
        summary_type='daily',
        is_edit_summary=False,
        early_return=weekly_suggested
    )


async def handle_restart_request(
    user_context,
    metadata
) -> DailyRecordResponse:
    """재시작 요청 처리

    Args:
        user_context: UserContext 객체
        metadata: UserMetadata 객체

    Returns:
        DailyRecordResponse: 처리 결과
    """
    from ...utils.utils import reset_session_data

    logger.info(f"[DailyRecordHandler] 재시작 요청 → 세션 초기화")
    reset_session_data(user_context)

    return DailyRecordResponse(
        ai_response=f"{metadata.name}님, 새로운 일일 기록을 시작하겠습니다! 오늘은 어떤 업무를 하셨나요?"
    )


async def handle_general_conversation(
    message: str,
    user_context,
    metadata,
    cached_today_turns: list,
    llm
) -> DailyRecordResponse:
    """일반 대화 처리 (질문 생성)

    Args:
        message: 사용자 메시지
        user_context: UserContext 객체
        metadata: UserMetadata 객체
        cached_today_turns: 캐시된 오늘 대화 히스토리
        llm: LLM 인스턴스

    Returns:
        DailyRecordResponse: 처리 결과
    """
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
    from ...prompt.daily_record_prompt import DAILY_CONVERSATION_SYSTEM_PROMPT

    from ...config.business_config import SUMMARY_SUGGESTION_THRESHOLD

    current_session_count = user_context.daily_session_data.get("conversation_count", 0)

    # 대화 횟수 먼저 증가
    new_count = current_session_count + 1
    user_context.daily_session_data["conversation_count"] = new_count

    logger.info(f"[DailyRecordHandler] 일반 대화 진행 ({new_count}회차)")
    logger.info(f"🔍 [DEBUG] new_count={new_count}, THRESHOLD={SUMMARY_SUGGESTION_THRESHOLD}, 조건={new_count >= SUMMARY_SUGGESTION_THRESHOLD}")

    # SUMMARY_SUGGESTION_THRESHOLD 이상 대화 시 요약 제안
    if new_count >= SUMMARY_SUGGESTION_THRESHOLD:
        logger.info(f"[DailyRecordHandler] {SUMMARY_SUGGESTION_THRESHOLD}회 대화 완료 → 요약 제안")
        return DailyRecordResponse(
            ai_response=f"{metadata.name}님, 오늘도 많은 이야기 나눠주셨네요! 지금까지 내용을 정리해드릴까요?"
        )

    # 캐시된 대화 히스토리 재사용
    recent_turns = cached_today_turns
    logger.info(f"[DailyRecordHandler] 캐시된 대화 재사용: {len(recent_turns)}턴")

    # 자연스러운 질문 생성
    system_prompt = DAILY_CONVERSATION_SYSTEM_PROMPT.format(
        name=metadata.name or "없음",
        job_title=metadata.job_title or "없음",
        total_years=metadata.total_years or "없음",
        job_years=metadata.job_years or "없음",
        career_goal=metadata.career_goal or "없음",
        project_name=metadata.project_name or "없음",
        recent_work=metadata.recent_work or "없음"
    )

    messages = [SystemMessage(content=system_prompt)]
    # 최근 3턴 사용 (메모리 최적화)
    for turn in recent_turns:
        messages.append(HumanMessage(content=turn["user_message"]))
        messages.append(AIMessage(content=turn["ai_message"]))
    messages.append(HumanMessage(content=message))

    response = await llm.ainvoke(messages)
    ai_response_final = response.content

    logger.info(f"[DailyRecordHandler] ✅ 질문 생성 완료, 대화 횟수: {new_count}")

    return DailyRecordResponse(
        ai_response=ai_response_final
    )


def _build_user_data(metadata, user_context) -> Dict[str, Any]:
    """UserContext에서 user_data dict 생성 (중복 DB 쿼리 방지용)

    Args:
        metadata: UserMetadata 객체
        user_context: UserContext 객체

    Returns:
        user_data dict
    """
    return {
        "name": metadata.name,
        "job_title": metadata.job_title,
        "project_name": metadata.project_name,
        "career_goal": metadata.career_goal,
        "total_years": metadata.total_years,
        "job_years": metadata.job_years,
        "recent_work": metadata.recent_work,
        "attendance_count": user_context.attendance_count,
        "daily_record_count": user_context.daily_record_count
    }


async def save_daily_conversation(
    db,
    user_id: str,
    message: str,
    result: DailyRecordResponse,
    user_context
) -> Tuple[int, Optional[int]]:
    """일일 대화 저장 + 카운트 증가 + 세션 업데이트 통합 처리

    Args:
        db: Database 인스턴스
        user_id: 사용자 ID
        message: 사용자 메시지
        result: DailyRecordResponse (처리 결과)
        user_context: UserContext 객체

    Returns:
        (updated_daily_count, new_attendance)
    """
    from ...database import update_daily_session_data

    # 🚨 중요: 요약 생성 시에만 카운트 증가 안 함
    # - 요약 수정(edit_summary)은 실제 대화 내용을 반영하므로 카운트 O
    # - 요약 생성(summary)은 기존 대화의 정리이므로 카운트 X
    should_increment = not (result.is_summary_response and not result.is_edit_summary)

    # 대화 저장 + 카운트 증가
    updated_daily_count, new_attendance = await save_and_increment(
        db, user_id, message, result.ai_response, user_context,
        is_summary=result.is_summary_response,
        summary_type=result.summary_type if result.is_summary_response else None,
        should_increment=should_increment
    )

    # 세션 데이터 업데이트
    await update_daily_session_data(
        db,
        user_id,
        user_context.daily_session_data,
        current_step="daily_recording" if user_context.daily_session_data else "daily_summary_completed"
    )

    current_session_count = user_context.daily_session_data.get("conversation_count", 0)
    logger.info(f"[DailyRecordHandler] 저장 완료: conversation_count={current_session_count}, daily_record_count={updated_daily_count}")

    return updated_daily_count, new_attendance


async def process_daily_record(
    db,
    user_id: str,
    message: str,
    user_intent: str,
    user_context,
    cached_today_turns: list,
    llm
) -> DailyRecordResponse:
    """일일 기록 요청 전체 처리

    Args:
        db: Database 인스턴스
        user_id: 사용자 ID
        message: 사용자 메시지
        user_intent: 사용자 의도 (classified_intent)
        user_context: UserContext 객체
        cached_today_turns: 캐시된 오늘 대화 히스토리
        llm: LLM 인스턴스

    Returns:
        DailyRecordResponse: 처리 결과
    """
    metadata = user_context.metadata

    # user_intent가 None인 경우 처리
    if user_intent is None:
        logger.error(f"[DailyRecordHandler] ❌ user_intent가 None입니다! 일반 대화로 fallback")
        return await handle_general_conversation(message, user_context, metadata, cached_today_turns, llm)

    # 오늘 기록 없이 요약 요청한 경우
    if "no_record_today" in user_intent:
        return await handle_no_record_today(user_context, metadata)

    # 거절 (요약 제안 거절)
    elif "rejection" in user_intent:
        return await handle_rejection(user_context, metadata)

    # 대화 종료 요청
    elif "end_conversation" in user_intent:
        return await handle_end_conversation(user_context, metadata)

    # 수정 불필요 (요약 만족)
    elif "no_edit_needed" in user_intent and user_context.daily_session_data.get("last_summary_at"):
        return await handle_no_edit_needed(user_context, metadata)

    # 요약 수정 요청
    elif "edit_summary" in user_intent:
        return await handle_edit_summary(db, user_id, message, user_context, metadata, llm)

    # 요약 요청
    elif "summary" in user_intent:
        return await handle_summary_request(db, user_id, message, user_context, metadata, llm)

    # 재시작 요청
    elif "restart" in user_intent:
        return await handle_restart_request(user_context, metadata)

    # 일반 대화 (질문 생성)
    else:
        return await handle_general_conversation(message, user_context, metadata, cached_today_turns, llm)


# =============================================================================
# Daily 헬퍼 함수 (utils.py에서 이동)
# =============================================================================

async def save_and_increment(
    db,
    user_id: str,
    user_message: str,
    ai_response: str,
    user_context,  # UserContext 타입
    is_summary: bool = False,
    summary_type: Optional[str] = None,
    should_increment: bool = True
) -> Tuple[int, Optional[int]]:
    """대화 저장 + daily_record_count 증가를 한 번에 처리

    Args:
        db: Database 인스턴스
        user_id: 사용자 ID
        user_message: 사용자 메시지
        ai_response: AI 응답 메시지
        user_context: UserContext 객체
        is_summary: 요약 응답 여부
        summary_type: 요약 타입 ('daily' 또는 'weekly')
        should_increment: 카운트 증가 여부 (요약 생성 시에는 False)

    Returns:
        (updated_daily_count, new_attendance)
        - updated_daily_count: 업데이트된 daily_record_count
        - new_attendance: 5회 달성 시 새로운 출석 일수 (아니면 None)

    Usage:
        daily_agent_node에서 대화 저장 + 카운트 증가 로직 통합
    """
    from ...database import increment_counts_with_check

    # 대화 저장
    await db.save_conversation_turn(
        user_id,
        user_message,
        ai_response,
        is_summary=is_summary,
        summary_type=summary_type if is_summary else None
    )

    # 카운트 증가 (필요 시)
    if should_increment:
        updated_daily_count, new_attendance = await increment_counts_with_check(db, user_id)

        if new_attendance:
            logger.info(f"[save_and_increment] 🎉 5회 달성! attendance_count 증가: {new_attendance}일차")
            user_context.attendance_count = new_attendance

        logger.info(f"[save_and_increment] daily_record_count 업데이트: {updated_daily_count}회")
        return updated_daily_count, new_attendance
    else:
        # 카운트 증가 안 함 (현재 값 유지)
        logger.info(f"[save_and_increment] 요약 생성 - daily_record_count 증가 안 함")
        return user_context.daily_record_count, None


async def check_and_suggest_weekly_summary(
    db,
    user_id: str,
    user_context,  # UserContext 타입
    current_attendance_count: int,
    ai_response: str,
    message: str,
    is_summary: bool = True,
    summary_type: str = 'daily'
) -> Tuple[str, bool]:
    """7일차 달성 시 주간 요약 제안 로직 (utils.py에서 이동)

    Args:
        db: Database 인스턴스
        user_id: 사용자 ID
        user_context: UserContext 객체
        current_attendance_count: 현재 출석 일수
        ai_response: 기본 AI 응답 (요약 텍스트 등)
        message: 사용자 메시지
        is_summary: 요약 응답 여부
        summary_type: 요약 타입 ('daily' 등)

    Returns:
        (ai_response_with_suggestion, should_suggest_weekly)
        - ai_response_with_suggestion: 주간 요약 제안 포함 응답
        - should_suggest_weekly: 주간 요약 제안 여부 (True/False)

    Usage:
        daily_agent_node에서 요약 생성/수정 후 7일차 체크
    """
    from ...database import set_weekly_summary_flag
    from ...config.business_config import DAILY_TURNS_THRESHOLD, WEEKLY_CYCLE_DAYS

    current_daily_count = user_context.daily_record_count

    # 주간 요약 주기 체크 (7, 14, 21일차 등)
    if current_attendance_count > 0 and current_attendance_count % WEEKLY_CYCLE_DAYS == 0 and current_daily_count >= DAILY_TURNS_THRESHOLD:
        # 중복 방지: 이미 주간요약 플래그가 있거나 이미 완료했으면 제안하지 않음
        conv_state = await db.get_conversation_state(user_id)
        temp_data = conv_state.get("temp_data", {}) if conv_state else {}
        weekly_summary_ready = temp_data.get("weekly_summary_ready", False)

        # 이번 주차에 주간요약을 이미 완료했는지 체크 (주차 단위 비교)
        weekly_completed_at_count = temp_data.get("weekly_completed_at_count")
        if weekly_completed_at_count:
            # 주차 번호로 비교 (1~7일차: 1주차, 8~14일차: 2주차, ...)
            current_week = (current_attendance_count - 1) // 7 + 1
            completed_week = (weekly_completed_at_count - 1) // 7 + 1
            already_completed_this_week = (current_week == completed_week)
        else:
            already_completed_this_week = False

        if not weekly_summary_ready and not already_completed_this_week:
            logger.info(f"[check_weekly_summary] 🎉 7일차 달성! (attendance={current_attendance_count}, daily={current_daily_count})")

            # 주간 요약 제안 메시지 추가
            ai_response_with_suggestion = f"{ai_response}\n\n🎉 7일차 달성! 주간 요약도 보여드릴까요?"

            # 대화 저장
            await db.save_conversation_turn(
                user_id,
                message,
                ai_response_with_suggestion,
                is_summary=is_summary,
                summary_type=summary_type
            )

            # 주간 요약 플래그 설정
            await set_weekly_summary_flag(db, user_id, current_attendance_count, user_context.daily_session_data)

            return ai_response_with_suggestion, True
        else:
            if weekly_summary_ready:
                logger.info(f"[check_weekly_summary] 7일차지만 이미 주간요약 플래그 존재 → 제안 생략")
            elif already_completed_this_week:
                logger.info(f"[check_weekly_summary] 7일차지만 이미 주간요약 완료 (completed_at={weekly_completed_at_count}) → 제안 생략")
            # 플래그가 이미 있거나 완료되었으면 일반 요약으로 처리 (제안 없이)
            return ai_response, False

    # 7일차 아님
    return ai_response, False
