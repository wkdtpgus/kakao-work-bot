"""요약 관련 복합 DB 로직 (V2 스키마)"""
from typing import Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# AI Service 스키마 import
from ..utils.schemas import (
    UserMetadataSchema,
    DailySummaryInput,
    WeeklyFeedbackInput
)


# =============================================================================
# 요약 저장 헬퍼 함수
# =============================================================================

async def save_daily_summary_v2(
    db,
    user_id: str,
    user_message: str,
    summary_content: str
) -> bool:
    """일일 요약 저장 (V2 스키마)

    ai_answer_messages 테이블에 is_summary=TRUE, summary_type='daily'로 저장

    Args:
        db: Database 인스턴스
        user_id: 카카오 사용자 ID
        user_message: 사용자 메시지 (요약 요청 메시지)
        summary_content: 일일 요약 내용

    Returns:
        bool: 저장 성공 여부
    """
    try:
        result = await db.save_conversation_turn(
            user_id=user_id,
            user_message=user_message,
            ai_message=summary_content,
            is_summary=True,
            summary_type='daily'
        )

        if result:
            logger.info(f"[SummaryRepoV2] 일일 요약 저장 완료: {user_id}")
            return True
        else:
            logger.error(f"[SummaryRepoV2] 일일 요약 저장 실패: {user_id}")
            return False

    except Exception as e:
        logger.error(f"[SummaryRepoV2] 일일 요약 저장 중 오류: {e}")
        return False


async def save_weekly_summary_v2(
    db,
    user_id: str,
    user_message: str,
    summary_content: str
) -> bool:
    """주간 요약 저장 (V2 스키마)

    ai_answer_messages 테이블에 is_summary=TRUE, summary_type='weekly'로 저장

    Args:
        db: Database 인스턴스
        user_id: 카카오 사용자 ID
        user_message: 사용자 메시지 (요약 요청 메시지)
        summary_content: 주간 요약 내용

    Returns:
        bool: 저장 성공 여부
    """
    try:
        result = await db.save_conversation_turn(
            user_id=user_id,
            user_message=user_message,
            ai_message=summary_content,
            is_summary=True,
            summary_type='weekly'
        )

        if result:
            logger.info(f"[SummaryRepoV2] 주간 요약 저장 완료: {user_id}")
            return True
        else:
            logger.error(f"[SummaryRepoV2] 주간 요약 저장 실패: {user_id}")
            return False

    except Exception as e:
        logger.error(f"[SummaryRepoV2] 주간 요약 저장 중 오류: {e}")
        return False


# =============================================================================
# 요약 조회 헬퍼 함수
# =============================================================================

async def get_daily_summaries_for_weekly_v2(
    db,
    user_id: str,
    limit: int = 7
) -> list:
    """주간 요약 생성을 위한 일일 요약 조회 (V2 스키마)

    하루에 여러 데일리 요약이 있는 경우, 각 날짜별 최신 요약만 반환합니다.
    RPC 함수 get_recent_daily_summaries_by_unique_dates() 사용

    Args:
        db: Database 인스턴스
        user_id: 카카오 사용자 ID
        limit: 조회할 고유 날짜 수 (기본 7개)

    Returns:
        list: [
            {
                "summary_content": "오늘의 요약...",
                "session_date": "2025-10-19",
                "created_at": "...",
                ...
            },
            ...
        ]
    """
    try:
        summaries = await db.get_daily_summaries_v2(user_id, limit=limit)
        logger.info(f"[SummaryRepoV2] 주간 요약용 일일 요약 조회: {len(summaries)}개")
        return summaries

    except Exception as e:
        logger.error(f"[SummaryRepoV2] 일일 요약 조회 중 오류: {e}")
        return []


async def get_all_summaries_v2(
    db,
    user_id: str,
    summary_type: Optional[str] = None,
    limit: int = 10
) -> list:
    """모든 요약 조회 (V2 스키마)

    ai_answer_messages 테이블에서 is_summary=TRUE인 메시지 조회

    Args:
        db: Database 인스턴스
        user_id: 카카오 사용자 ID
        summary_type: 요약 타입 ('daily', 'weekly_v1', 'weekly_v2', None이면 전체)
        limit: 조회할 요약 개수

    Returns:
        list: 요약 목록
    """
    try:
        if not db.supabase:
            return []

        query = db.supabase.table("ai_answer_messages") \
            .select("uuid, kakao_user_id, content, summary_type, created_at") \
            .eq("kakao_user_id", user_id) \
            .eq("is_summary", True)

        if summary_type:
            query = query.eq("summary_type", summary_type)

        response = query.order("created_at", desc=True) \
            .limit(limit) \
            .execute()

        summaries = response.data if response.data else []
        logger.info(
            f"[SummaryRepoV2] 요약 조회 완료: {user_id} "
            f"(type={summary_type or 'all'}, count={len(summaries)})"
        )
        return summaries

    except Exception as e:
        logger.error(f"[SummaryRepoV2] 요약 조회 중 오류: {e}")
        return []


# =============================================================================
# V2 스키마 - 주간 요약 준비 체크 로직 (평일 기반)
# =============================================================================

async def check_weekly_summary_ready(
    db,
    user_id: str,
    weekday_record_count: int = None
) -> Tuple[bool, int]:
    """주간 요약 생성 준비 여부 체크 (V2 스키마 - 평일 기반)

    이번 주 평일(월~금) 작성 일수가 2일 이상인지 확인
    주말(토~일)에만 제공 가능

    Args:
        db: Database 인스턴스
        user_id: 카카오 사용자 ID
        weekday_record_count: 이번 주 평일 작성 일수 (None이면 자동 조회)

    Returns:
        (is_ready, weekday_count): 준비 여부와 평일 작성 일수
    """
    try:
        from datetime import datetime

        # weekday_record_count가 전달되지 않으면 temp_data에서 조회
        if weekday_record_count is None:
            conv_state = await db.get_conversation_state(user_id)
            temp_data = conv_state.get("temp_data", {}) if conv_state else {}
            weekday_record_count = temp_data.get("weekday_record_count", 0)

        # 주말(토~일) 체크
        now = datetime.now()
        weekday = now.weekday()  # 0=월, 1=화, ..., 5=토, 6=일
        is_weekend = weekday >= 5

        # 평일 2일 이상 작성 + 주말이면 준비 완료
        is_ready = is_weekend and weekday_record_count >= 2

        logger.info(
            f"[SummaryRepoV2] 주간 요약 준비 체크: "
            f"weekday_count={weekday_record_count}, is_weekend={is_weekend}, ready={is_ready}"
        )

        return is_ready, weekday_record_count

    except Exception as e:
        logger.error(f"[SummaryRepoV2] 주간 요약 준비 체크 중 오류: {e}")
        return False, 0


# =============================================================================
# 데이터 준비 함수 (AI Service용)
# =============================================================================

async def prepare_daily_summary_data(
    db,
    user_id: str,
    today_turns: list,
    user_correction: Optional[str] = None,
    user_data: Optional[dict] = None,
    latest_summary: Optional[str] = None
) -> DailySummaryInput:
    """데일리 요약 생성에 필요한 데이터 준비

    AI 서비스(summary_generator)가 DB에 직접 접근하지 않도록
    필요한 모든 데이터를 미리 조회하고 포맷팅하여 제공

    Args:
        db: Database 인스턴스
        user_id: 카카오 사용자 ID
        today_turns: 오늘의 대화 턴 리스트 (수정 모드에서는 빈 리스트 가능)
        user_correction: 사용자의 수정 요청 (edit_summary 시 사용)
        user_data: 사용자 정보 (캐시된 경우 전달, 없으면 조회)
        latest_summary: 최신 생성된 요약 (edit_summary 시 사용, 있으면 수정 모드)

    Returns:
        DailySummaryInput: AI 서비스용 입력 데이터
    """
    try:
        # 사용자 정보 (캐시 재사용 or 조회)
        user = user_data if user_data else await db.get_user(user_id)

        if not user:
            logger.warning(f"[SummaryRepoV2] 사용자 정보 없음: {user_id}")
            # 기본값 반환
            return DailySummaryInput(
                user_metadata=UserMetadataSchema(),
                conversation_context="",
                attendance_count=0,
                daily_record_count=0
            )

        # 대화 텍스트 포맷팅 (오래된 대화 → 최신 대화 순서)
        conversation_lines = []
        for turn in reversed(today_turns):
            conversation_lines.append(f"사용자: {turn.get('user_message', '')}")
            conversation_lines.append(f"봇: {turn.get('ai_message', '')}")

        conversation_context = "\n".join(conversation_lines)

        logger.info(f"[SummaryRepoV2] 데일리 요약 데이터 준비 완료 (대화 {len(today_turns)}개)")

        return DailySummaryInput(
            user_metadata=UserMetadataSchema(
                name=user.get("name") or "사용자",
                job_title=user.get("job_title") or "직무 정보 없음",
                project_name=user.get("project_name") or "프로젝트 정보 없음",
                career_goal=user.get("career_goal") or "목표 정보 없음",
                total_years=user.get("total_years"),
                job_years=user.get("job_years"),
                recent_work=user.get("recent_work")
            ),
            conversation_context=conversation_context,
            attendance_count=user.get("attendance_count", 0),
            daily_record_count=user.get("daily_record_count", 0),
            user_correction=user_correction,
            latest_summary=latest_summary
        )

    except Exception as e:
        logger.error(f"[SummaryRepoV2] 데일리 요약 데이터 준비 중 오류: {e}")
        raise


async def prepare_weekly_feedback_data(
    db,
    user_id: str,
    user_data: Optional[dict] = None
) -> WeeklyFeedbackInput:
    """주간 피드백 생성에 필요한 데이터 준비

    AI 서비스(weekly_feedback_generator)가 DB에 직접 접근하지 않도록
    필요한 모든 데이터를 미리 조회하고 포맷팅하여 제공

    Args:
        db: Database 인스턴스
        user_id: 카카오 사용자 ID
        user_data: 사용자 정보 (캐시된 경우 전달, 없으면 조회)

    Returns:
        WeeklyFeedbackInput: AI 서비스용 입력 데이터
    """
    try:
        # 병렬 DB 쿼리 (user_data가 캐시되어 있으면 재사용)
        import asyncio
        if user_data:
            user, daily_summaries = user_data, await db.get_daily_summaries_v2(user_id, limit=7)
        else:
            user, daily_summaries = await asyncio.gather(
                db.get_user(user_id),
                db.get_daily_summaries_v2(user_id, limit=7)
            )

        if not user:
            logger.warning(f"[SummaryRepoV2] 사용자 정보 없음: {user_id}")
            # 기본값 반환
            return WeeklyFeedbackInput(
                user_metadata=UserMetadataSchema(),
                formatted_context=""
            )

        if not daily_summaries or len(daily_summaries) == 0:
            logger.warning(f"[SummaryRepoV2] 데일리 요약 없음 → 최근 대화 히스토리로 대체")

            # 최근 대화 히스토리로 fallback
            recent_turns = await db.get_recent_turns_v2(user_id, limit=20)

            formatted_messages = []
            for turn in recent_turns:
                formatted_messages.append(f"사용자: {turn.get('user_message', '')}")
                formatted_messages.append(f"AI: {turn.get('ai_message', '')}")

            formatted_context = "[최근 대화]\n" + "\n".join(formatted_messages)
        else:
            # 데일리 요약 기반 컨텍스트 구성
            formatted_summaries = []
            for summary in reversed(daily_summaries):  # 오래된 순으로 정렬
                session_date = summary.get("session_date", "날짜 미상")
                content = summary.get("summary_content", "")
                formatted_summaries.append(f"**{session_date}**\n{content}")

            formatted_context = "\n\n".join(formatted_summaries)
            logger.info(f"[SummaryRepoV2] 데일리 요약 기반 컨텍스트 구성 완료 ({len(daily_summaries)}개)")

        return WeeklyFeedbackInput(
            user_metadata=UserMetadataSchema(
                name=user.get("name") or "사용자",
                job_title=user.get("job_title") or "직무 정보 없음",
                career_goal=user.get("career_goal") or "목표 정보 없음"
            ),
            formatted_context=formatted_context
        )

    except Exception as e:
        logger.error(f"[SummaryRepoV2] 주간 피드백 데이터 준비 중 오류: {e}")
        raise


# =============================================================================
# 주간요약 조건 체크 헬퍼 함수
# =============================================================================

async def count_this_week_weekday_records(db, user_id: str) -> int:
    """이번 주 평일(월~금) 일일 요약 개수를 DB에서 동적으로 계산

    Args:
        db: Database 인스턴스
        user_id: 카카오 사용자 ID

    Returns:
        int: 이번 주 평일 일일 요약 개수 (0 이상)
    """
    from datetime import datetime, timedelta

    try:
        now = datetime.now()

        # 이번 주 월요일 계산
        weekday = now.weekday()  # 0=월, 1=화, ..., 6=일
        days_since_monday = weekday
        monday = (now - timedelta(days=days_since_monday)).date()

        # 이번 주 금요일 계산
        friday = monday + timedelta(days=4)

        # DB에서 이번 주 월~금 사이의 일일 요약 개수 조회
        # ai_answer_messages 테이블에서 is_summary=TRUE, summary_type='daily'인 레코드 카운트
        records = await db.get_summaries_between_dates(
            user_id=user_id,
            start_date=monday.isoformat(),
            end_date=friday.isoformat(),
            summary_type='daily'
        )

        count = len(records) if records else 0
        logger.info(f"[SummaryRepo] 이번 주 평일 일일 요약 개수: {count} (기간: {monday} ~ {friday})")

        return count

    except Exception as e:
        logger.warning(f"[SummaryRepo] 이번 주 평일 기록 개수 조회 실패: {e}, 기본값 0 반환")
        return 0
