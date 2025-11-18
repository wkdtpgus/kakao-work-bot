"""대화 관련 복합 DB 로직"""
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


async def get_today_conversations(db, user_id: str) -> Tuple[list, Optional[Dict]]:
    """오늘 날짜의 대화 히스토리 + conversation_state 조회 (daily_agent용)

    Args:
        db: Database 인스턴스
        user_id: 카카오 사용자 ID

    Returns:
        (today_turns, conv_state): 오늘 대화 목록과 conversation_state
    """
    today = datetime.now().date().isoformat()

    # 병렬 쿼리 (V2 스키마 사용)
    import asyncio
    today_turns, conv_state = await asyncio.gather(
        db.get_conversation_history_by_date_v2(user_id, today, limit=50),
        db.get_conversation_state(user_id)
    )

    logger.info(f"[ConvRepo V2] 오늘 대화 로드: {len(today_turns)}개")
    return today_turns, conv_state


async def get_weekly_summary_flag(db, user_id: str) -> Tuple[bool, Optional[int]]:
    """주간 요약 생성 플래그 확인 (weekly_agent용)

    Args:
        db: Database 인스턴스
        user_id: 카카오 사용자 ID

    Returns:
        (is_ready, attendance_count): 주간 요약 준비 여부와 attendance_count
    """
    conv_state = await db.get_conversation_state(user_id)

    if not conv_state:
        return False, None

    temp_data = conv_state.get("temp_data", {})
    weekly_summary_ready = temp_data.get("weekly_summary_ready", False)
    daily_count_verified = temp_data.get("daily_count_verified", False)
    attendance_count = temp_data.get("attendance_count")

    is_ready = weekly_summary_ready and daily_count_verified and attendance_count is not None

    return is_ready, attendance_count


async def clear_weekly_summary_flag(db, user_id: str) -> None:
    """주간 요약 플래그 정리 (weekly_agent 완료 후)

    Args:
        db: Database 인스턴스
        user_id: 카카오 사용자 ID
    """
    conv_state = await db.get_conversation_state(user_id)
    temp_data = conv_state.get("temp_data", {}) if conv_state else {}

    # 현재 주차 저장 (중복 방지용)
    current_week = temp_data.get("weekday_count_week")

    # 플래그 제거
    temp_data.pop("weekly_summary_ready", None)
    temp_data.pop("attendance_count", None)
    temp_data.pop("daily_count_verified", None)

    # 완료 시점의 주차 기록 (중복 제안 방지)
    if current_week:
        temp_data["weekly_completed_week"] = current_week

    await db.upsert_conversation_state(
        user_id,
        current_step="weekly_feedback_completed",
        temp_data=temp_data
    )
    logger.info(f"[ConvRepo] 주간 요약 플래그 정리 완료 (completed_week={current_week})")


async def update_daily_session_data(
    db,
    user_id: str,
    daily_session_data: Dict[str, Any],
    current_step: str = "daily_recording"
) -> None:
    """daily_session_data 업데이트 (대화 횟수 등)

    Args:
        db: Database 인스턴스
        user_id: 카카오 사용자 ID
        daily_session_data: 업데이트할 세션 데이터
        current_step: 현재 단계
    """
    conv_state = await db.get_conversation_state(user_id)
    existing_temp_data = conv_state.get("temp_data", {}) if conv_state else {}
    existing_temp_data["daily_session_data"] = daily_session_data or {}

    await db.upsert_conversation_state(
        user_id,
        current_step=current_step,
        temp_data=existing_temp_data
    )
    logger.debug(f"[ConvRepo] daily_session_data 업데이트: {daily_session_data}")


async def handle_rejection_flag(db, user_id: str) -> bool:
    """거절 플래그 처리 (주간 요약 제안 거절 시)

    Args:
        db: Database 인스턴스
        user_id: 카카오 사용자 ID

    Returns:
        bool: 플래그가 있었는지 여부
    """
    conv_state = await db.get_conversation_state(user_id)
    temp_data = conv_state.get("temp_data", {}) if conv_state else {}

    had_flag = temp_data.get("weekly_summary_ready", False)

    if had_flag:
        temp_data.pop("weekly_summary_ready", None)
        temp_data.pop("attendance_count", None)
        await db.upsert_conversation_state(
            user_id,
            current_step="weekly_feedback_rejected",
            temp_data=temp_data
        )
        logger.info(f"[ConvRepo] 주간 요약 거절 플래그 정리 완료")

    return had_flag
