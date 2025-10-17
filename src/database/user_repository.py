"""사용자 관련 복합 DB 로직"""
from typing import Optional, Tuple
from datetime import datetime
from .schemas import UserSchema
import logging

logger = logging.getLogger(__name__)


async def get_user_with_context(db, user_id: str) -> Tuple[Optional[UserSchema], "UserContext"]:
    """사용자 정보 + UserContext 구성 (router_node용)

    Args:
        db: Database 인스턴스
        user_id: 카카오 사용자 ID

    Returns:
        (user_data, user_context): UserSchema와 UserContext 튜플
    """
    from ..chatbot.state import UserContext, UserMetadata, OnboardingStage

    # 병렬 DB 쿼리
    import asyncio
    user_dict, conv_state, recent_messages = await asyncio.gather(
        db.get_user(user_id),
        db.get_conversation_state(user_id),
        db.get_conversation_history(user_id, limit=1)
    )

    # 신규 사용자
    if not user_dict:
        user_context = UserContext(
            user_id=user_id,
            onboarding_stage=OnboardingStage.NOT_STARTED,
            metadata=UserMetadata()
        )
        return None, user_context

    # UserSchema 변환
    user = UserSchema(**user_dict)

    # 기존 사용자 - 메타데이터 구성
    DATA_FIELDS = ["name", "job_title", "total_years", "job_years", "career_goal",
                   "project_name", "recent_work", "job_meaning", "important_thing"]

    metadata = UserMetadata(**{
        k: getattr(user, k) for k in DATA_FIELDS
    })

    # conversation_states에서 세션 상태 복원
    daily_session_data = {}

    if conv_state and conv_state.get("temp_data"):
        temp_data = conv_state["temp_data"]
        metadata.field_attempts = temp_data.get("field_attempts", {})
        metadata.field_status = temp_data.get("field_status", {})

        # daily_session_data는 날짜 기반으로 리셋
        today = datetime.now().date().isoformat()

        if recent_messages and len(recent_messages) > 0:
            last_message_date = recent_messages[0].get("created_at", "")[:10]

            if last_message_date == today:
                # 오늘 대화가 있으면 세션 유지
                daily_session_data = temp_data.get("daily_session_data", {})
                logger.info(f"[UserRepo] 세션 유지: conversation_count={daily_session_data.get('conversation_count', 0)}")
            else:
                # 다른 날 대화면 세션 리셋
                logger.info(f"[UserRepo] 세션 리셋: last={last_message_date}, today={today}")
        else:
            logger.info(f"[UserRepo] 세션 리셋 (대화 히스토리 없음)")

    # 온보딩 완료 체크
    is_complete = all([
        metadata.name,
        metadata.job_title,
        metadata.total_years,
        metadata.job_years,
        metadata.career_goal,
        metadata.project_name,
        metadata.recent_work,
        metadata.job_meaning,
        metadata.important_thing
    ])

    user_context = UserContext(
        user_id=user_id,
        onboarding_stage=OnboardingStage.COMPLETED if is_complete else OnboardingStage.COLLECTING_BASIC,
        metadata=metadata,
        daily_record_count=user.attendance_count,
        last_record_date=user.last_record_date,
        daily_session_data=daily_session_data
    )

    return user, user_context


async def check_and_reset_daily_count(db, user_id: str) -> Tuple[int, bool]:
    """날짜 변경 체크 및 daily_record_count 리셋 (daily_agent용)

    Args:
        db: Database 인스턴스
        user_id: 카카오 사용자 ID

    Returns:
        (current_count, was_reset): 현재 카운트와 리셋 여부
    """
    user_dict = await db.get_user(user_id)

    if not user_dict:
        return 0, False

    user = UserSchema(**user_dict)
    today = datetime.now().date().isoformat()
    last_date = user.updated_at[:10] if user.updated_at else None

    # 날짜가 바뀌었으면 리셋
    if last_date and last_date != today:
        logger.info(f"[UserRepo] 📅 날짜 변경 감지: {last_date} → {today}")
        await db.create_or_update_user(user_id, {"daily_record_count": 0})
        return 0, True

    return user.daily_record_count, False


async def increment_counts_with_check(db, user_id: str) -> Tuple[int, Optional[int]]:
    """daily_record_count 증가 및 5회 달성 시 attendance_count 증가

    Args:
        db: Database 인스턴스
        user_id: 카카오 사용자 ID

    Returns:
        (new_daily_count, new_attendance_count):
            - new_daily_count: 증가된 daily_record_count
            - new_attendance_count: 5회 달성 시 증가된 attendance_count, 아니면 None
    """
    # daily_record_count 증가
    new_daily_count = await db.increment_daily_record_count(user_id)

    # 5회가 되는 순간 attendance_count 증가
    if new_daily_count == 5:
        user_dict = await db.get_user(user_id)
        user = UserSchema(**user_dict)
        current_attendance = user.attendance_count
        new_attendance = await db.increment_attendance_count(user_id, new_daily_count)
        logger.info(f"[UserRepo] 🎉 5회 달성! attendance: {current_attendance} → {new_attendance}일차")
        return new_daily_count, new_attendance

    return new_daily_count, None


async def save_onboarding_metadata(db, user_id: str, metadata: "UserMetadata") -> None:
    """온보딩 메타데이터 저장 (users + conversation_states)

    Args:
        db: Database 인스턴스
        user_id: 카카오 사용자 ID
        metadata: UserMetadata 객체
    """
    # users 테이블 업데이트 (null 값 및 내부 필드 제외)
    db_data = {
        k: v for k, v in metadata.dict().items()
        if v is not None and k not in ["field_attempts", "field_status"]
    }

    if db_data:
        await db.create_or_update_user(user_id, db_data)

    # conversation_states.temp_data에 field_attempts, field_status 저장
    temp_data = {
        "field_attempts": metadata.field_attempts,
        "field_status": metadata.field_status
    }

    logger.debug(f"[UserRepo] 저장할 field_attempts: {metadata.field_attempts}")
    logger.debug(f"[UserRepo] 저장할 field_status: {metadata.field_status}")

    await db.upsert_conversation_state(
        user_id,
        current_step="onboarding",
        temp_data=temp_data
    )


async def complete_onboarding(db, user_id: str) -> None:
    """온보딩 완료 처리

    Args:
        db: Database 인스턴스
        user_id: 카카오 사용자 ID
    """
    await db.create_or_update_user(user_id, {"onboarding_completed": True})
    logger.info(f"[UserRepo] ✅ onboarding_completed = True")


async def get_onboarding_history(db, user_id: str) -> Tuple[int, list]:
    """온보딩 대화 히스토리 조회 및 과다 감지

    Args:
        db: Database 인스턴스
        user_id: 카카오 사용자 ID

    Returns:
        (total_count, recent_messages): 전체 개수와 최근 3개 메시지
    """
    import asyncio
    total_count, recent_messages = await asyncio.gather(
        db.count_messages(user_id),
        db.get_conversation_history(user_id, limit=3)
    )

    # 10개 넘으면 초기화 (실패 패턴 누적 방지)
    if total_count > 10:
        logger.warning(f"[UserRepo] 대화 히스토리 과다 감지 ({total_count}개) - 초기화")
        await db.delete_conversations(user_id)
        return 0, []

    return total_count, recent_messages
