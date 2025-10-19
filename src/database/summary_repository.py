"""요약 관련 복합 DB 로직 (V2 스키마)"""
from typing import Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# V2 스키마 - 요약 저장 헬퍼 함수
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
# V2 스키마 - 요약 조회 헬퍼 함수
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

    summary_messages_view를 통해 요약 조회

    Args:
        db: Database 인스턴스
        user_id: 카카오 사용자 ID
        summary_type: 요약 타입 ('daily', 'weekly', None이면 전체)
        limit: 조회할 요약 개수

    Returns:
        list: 요약 목록
    """
    try:
        if not db.supabase:
            return []

        query = db.supabase.table("summary_messages_view") \
            .select("*") \
            .eq("kakao_user_id", user_id)

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
# V2 스키마 - 7일차 체크 로직
# =============================================================================

async def check_weekly_summary_ready(
    db,
    user_id: str,
    attendance_count: int
) -> Tuple[bool, int]:
    """주간 요약 생성 준비 여부 체크 (V2 스키마)

    attendance_count가 7의 배수이고, 실제 일일 요약이 5개 이상인지 확인

    Args:
        db: Database 인스턴스
        user_id: 카카오 사용자 ID
        attendance_count: 현재 출석 카운트

    Returns:
        (is_ready, daily_summary_count): 준비 여부와 일일 요약 개수
    """
    try:
        # 7의 배수가 아니면 준비 안 됨
        if attendance_count == 0 or attendance_count % 7 != 0:
            return False, 0

        # 최근 7개 일일 요약 조회
        daily_summaries = await db.get_daily_summaries_v2(user_id, limit=7)
        daily_count = len(daily_summaries)

        # 5개 이상이어야 주간 요약 생성
        is_ready = daily_count >= 5

        logger.info(
            f"[SummaryRepoV2] 주간 요약 준비 체크: "
            f"attendance={attendance_count}, daily_count={daily_count}, ready={is_ready}"
        )

        return is_ready, daily_count

    except Exception as e:
        logger.error(f"[SummaryRepoV2] 주간 요약 준비 체크 중 오류: {e}")
        return False, 0
