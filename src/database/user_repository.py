"""사용자 관련 복합 DB 로직"""
from typing import Optional, Tuple, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


async def get_user_with_context(db, user_id: str) -> Tuple[Optional[Dict[str, Any]], "UserContext"]:
    """사용자 정보 + UserContext 구성 (router_node용)

    Args:
        db: Database 인스턴스
        user_id: 카카오 사용자 ID

    Returns:
        (user_data, user_context): 사용자 정보 dict와 UserContext 튜플
    """
    from ..chatbot.state import UserContext, UserMetadata, OnboardingStage

    # 병렬 DB 쿼리 (V2 스키마)
    import asyncio
    user, conv_state, recent_turns = await asyncio.gather(
        db.get_user(user_id),
        db.get_conversation_state(user_id),
        db.get_recent_turns_v2(user_id, limit=1)
    )

    # 신규 사용자 (users 테이블에 레코드 없음)
    if not user:
        # conversation_states에서 온보딩 진행 상태 로드
        metadata = UserMetadata()
        onboarding_stage = OnboardingStage.NOT_STARTED

        if conv_state and conv_state.get("temp_data"):
            temp_data = conv_state["temp_data"]
            metadata.field_attempts = temp_data.get("field_attempts", {})
            metadata.field_status = temp_data.get("field_status", {})

            # 온보딩이 진행 중이면 COLLECTING_BASIC으로 설정
            if metadata.field_attempts or metadata.field_status:
                onboarding_stage = OnboardingStage.COLLECTING_BASIC
                logger.info(f"[UserRepo] 온보딩 진행 중 - attempts={metadata.field_attempts}")
            else:
                logger.info(f"[UserRepo] 온보딩 시작 전")

        user_context = UserContext(
            user_id=user_id,
            onboarding_stage=onboarding_stage,
            metadata=metadata
        )
        return None, user_context

    # user는 dict 객체

    # 기존 사용자 - 메타데이터 구성
    DATA_FIELDS = ["name", "job_title", "total_years", "job_years", "career_goal",
                   "project_name", "recent_work", "job_meaning", "important_thing"]

    metadata = UserMetadata(**{
        k: user.get(k) for k in DATA_FIELDS
    })

    # conversation_states에서 세션 상태 복원
    daily_session_data = {}

    if conv_state and conv_state.get("temp_data"):
        temp_data = conv_state["temp_data"]
        metadata.field_attempts = temp_data.get("field_attempts", {})
        metadata.field_status = temp_data.get("field_status", {})

        # daily_session_data는 날짜 기반으로 리셋 (V2 스키마)
        today = datetime.now().date().isoformat()

        if recent_turns and len(recent_turns) > 0:
            # V2: session_date 또는 created_at 사용
            last_turn_date = recent_turns[0].get("session_date") or recent_turns[0].get("created_at", "")[:10]

            if last_turn_date == today:
                # 오늘 대화가 있으면 세션 유지
                daily_session_data = temp_data.get("daily_session_data", {})
                logger.info(f"[UserRepo] 세션 유지: conversation_count={daily_session_data.get('conversation_count', 0)}")
            else:
                # 다른 날 대화면 세션 리셋
                logger.info(f"[UserRepo] 세션 리셋: last={last_turn_date}, today={today}")
        else:
            logger.info(f"[UserRepo] 세션 리셋 (대화 히스토리 없음)")

    # 온보딩 완료 체크 - onboarding_completed 플래그 기반 (필드 체크 제거)
    # complete_onboarding()에서 설정한 플래그를 신뢰
    onboarding_completed = user.get("onboarding_completed", False)

    user_context = UserContext(
        user_id=user_id,
        onboarding_stage=OnboardingStage.COMPLETED if onboarding_completed else OnboardingStage.COLLECTING_BASIC,
        metadata=metadata,
        attendance_count=user.get("attendance_count", 0),
        daily_record_count=user.get("daily_record_count", 0),
        last_record_date=user.get("last_record_date"),
        daily_session_data=daily_session_data
    )

    logger.info(f"[UserRepo] onboarding_completed={onboarding_completed}, stage={user_context.onboarding_stage}")

    return user, user_context


async def check_and_reset_daily_count(db, user_id: str) -> Tuple[int, bool]:
    """날짜 변경 체크 및 daily_record_count 리셋 (daily_agent용)

    Args:
        db: Database 인스턴스
        user_id: 카카오 사용자 ID

    Returns:
        (current_count, was_reset): 현재 카운트와 리셋 여부
    """
    user = await db.get_user(user_id)

    if not user:
        return 0, False
    today = datetime.now().date()
    last_record_date = user.get("last_record_date")

    # 날짜가 바뀌었으면 리셋 (주간요약 플래그도 함께 정리)
    if last_record_date and last_record_date != today.isoformat():
        logger.info(f"[UserRepo] 📅 날짜 변경 감지: {last_record_date} → {today}")
        await db.create_or_update_user(user_id, {"daily_record_count": 0})

        # 주간요약 플래그도 날짜 변경 시 정리
        conv_state = await db.get_conversation_state(user_id)
        if conv_state and conv_state.get("temp_data", {}).get("weekly_summary_ready"):
            temp_data = conv_state.get("temp_data", {})
            temp_data.pop("weekly_summary_ready", None)
            temp_data.pop("attendance_count", None)  # attendance_count도 정리
            await db.upsert_conversation_state(user_id, current_step=conv_state.get("current_step"), temp_data=temp_data)
            logger.info(f"[UserRepo] 🧹 날짜 변경으로 weekly_summary_ready 플래그 정리")

        return 0, True

    return user.get("daily_record_count", 0), False


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
    from ..config.business_config import DAILY_TURNS_THRESHOLD

    # daily_record_count 증가
    new_daily_count = await db.increment_daily_record_count(user_id)

    # DAILY_TURNS_THRESHOLD 달성 시 attendance_count 증가
    if new_daily_count == DAILY_TURNS_THRESHOLD:
        user = await db.get_user(user_id)
        current_attendance = user.get("attendance_count", 0) if user else 0
        new_attendance = await db.increment_attendance_count(user_id, new_daily_count)
        logger.info(f"[UserRepo] 🎉 {DAILY_TURNS_THRESHOLD}회 달성! attendance: {current_attendance} → {new_attendance}일차")
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

    logger.info(f"[UserRepo] save_onboarding_metadata - metadata.dict(): {metadata.dict()}")
    logger.info(f"[UserRepo] save_onboarding_metadata - db_data: {db_data}")

    # users 테이블은 실제 데이터가 있을 때만 저장 (name 등 NOT NULL 제약 조건 때문)
    if db_data:
        await db.create_or_update_user(user_id, db_data)

    # conversation_states.temp_data에 field_attempts, field_status 저장 (기존 데이터 병합)
    conv_state = await db.get_conversation_state(user_id)
    existing_temp_data = conv_state.get("temp_data", {}) if conv_state else {}

    # 기존 temp_data에 field_attempts, field_status만 업데이트 (onboarding_messages 유지)
    existing_temp_data.update({
        "field_attempts": metadata.field_attempts,
        "field_status": metadata.field_status
    })

    logger.debug(f"[UserRepo] 저장할 field_attempts: {metadata.field_attempts}")
    logger.debug(f"[UserRepo] 저장할 field_status: {metadata.field_status}")

    await db.upsert_conversation_state(
        user_id,
        current_step="onboarding",
        temp_data=existing_temp_data
    )


async def complete_onboarding(db, user_id: str) -> None:
    """온보딩 완료 처리 및 온보딩 데이터 정리

    온보딩이 완료되면:
    1. onboarding_completed 플래그 설정
    2. temp_data의 온보딩 컨텍스트 삭제 (daily_session_data는 유지)
    3. DB에 저장된 온보딩 턴 삭제 (혹시 있을 경우 대비)

    Args:
        db: Database 인스턴스
        user_id: 카카오 사용자 ID
    """
    # 1. 온보딩 완료 플래그 설정
    await db.create_or_update_user(user_id, {"onboarding_completed": True})
    logger.info(f"[UserRepo] ✅ onboarding_completed = True")

    # 2. temp_data의 온보딩 컨텍스트 삭제
    conv_state = await db.get_conversation_state(user_id)
    if conv_state and conv_state.get("temp_data"):
        temp_data = conv_state["temp_data"]

        # 온보딩 관련 필드만 삭제 (daily_session_data는 유지)
        temp_data.pop("onboarding_messages", None)
        temp_data.pop("field_attempts", None)
        temp_data.pop("field_status", None)
        temp_data.pop("question_turn", None)

        await db.upsert_conversation_state(user_id, current_step="completed", temp_data=temp_data)
        logger.info(f"[UserRepo] 🗑️ temp_data 온보딩 컨텍스트 삭제 완료")

    # 3. DB 온보딩 대화 턴 삭제 (혹시 저장된 경우 대비, V2 스키마)
    try:
        if not db.supabase:
            logger.warning(f"[UserRepo] Supabase 미연결 - 온보딩 턴 삭제 스킵")
            return

        # 2-1. 삭제할 턴 조회
        turns_response = db.supabase.table("message_history") \
            .select("uuid, user_answer_key, ai_answer_key") \
            .eq("kakao_user_id", user_id) \
            .execute()

        if not turns_response.data:
            logger.info(f"[UserRepo] 삭제할 온보딩 턴 없음")
            return

        turn_count = len(turns_response.data)
        user_answer_keys = [turn["user_answer_key"] for turn in turns_response.data]
        ai_answer_keys = [turn["ai_answer_key"] for turn in turns_response.data]

        # 2-2. message_history 삭제
        db.supabase.table("message_history") \
            .delete() \
            .eq("kakao_user_id", user_id) \
            .execute()

        # 2-3. user_answer_messages 삭제
        if user_answer_keys:
            db.supabase.table("user_answer_messages") \
                .delete() \
                .in_("uuid", user_answer_keys) \
                .execute()

        # 2-4. ai_answer_messages 삭제
        if ai_answer_keys:
            db.supabase.table("ai_answer_messages") \
                .delete() \
                .in_("uuid", ai_answer_keys) \
                .execute()

        logger.info(f"[UserRepo] 🗑️ 온보딩 턴 삭제 완료: {turn_count}개")

    except Exception as e:
        logger.error(f"[UserRepo] 온보딩 턴 삭제 실패: {e}")
        import traceback
        traceback.print_exc()


async def get_onboarding_history(db, user_id: str) -> Tuple[int, list]:
    """온보딩 대화 히스토리 조회 (V2 스키마)

    Args:
        db: Database 인스턴스
        user_id: 카카오 사용자 ID

    Returns:
        (total_count, recent_turns): 전체 턴 개수와 최근 3개 턴
    """
    # V2: 최근 턴만 조회 (온보딩 중에는 대화가 많지 않음)
    recent_turns = await db.get_recent_turns_v2(user_id, limit=10)
    total_count = len(recent_turns)

    # V2에서는 개별 턴 관리로 삭제 기능 불필요
    # 온보딩 실패 패턴은 field_attempts로 감지

    return total_count, recent_turns[:3]  # 최근 3개만 반환
