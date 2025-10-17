"""요약 관련 복합 DB 로직"""
from typing import Optional
from datetime import datetime
from .schemas import DailyRecordSchema, WeeklySummarySchema
import logging

logger = logging.getLogger(__name__)


async def save_daily_summary_with_checks(
    db,
    user_id: str,
    summary_content: str,
    user_dict: dict,
    attendance_count: int
) -> tuple[bool, Optional[int]]:
    """일일 요약 저장 및 7일차 체크

    Args:
        db: Database 인스턴스
        user_id: 카카오 사용자 ID
        summary_content: 일일 요약 내용
        user_dict: 사용자 정보 딕셔너리 (UserSchema 변환 전)
        attendance_count: 현재 attendance_count

    Returns:
        (is_7th_day, daily_record_count): 7일차 여부와 현재 daily_record_count
    """
    # 일일 요약 저장
    today = datetime.now().date().isoformat()
    await db.save_daily_record(user_id, summary_content, record_date=today)

    # 7일차 체크 (attendance_count % 7 == 0 AND daily_record_count >= 5)
    daily_record_count = user_dict.get("daily_record_count", 0)
    is_7th_day = (attendance_count > 0 and
                  attendance_count % 7 == 0 and
                  daily_record_count >= 5)

    logger.info(
        f"[SummaryRepo] 일일 요약 저장 완료 - "
        f"7일차 여부: {is_7th_day} (attendance={attendance_count}, daily={daily_record_count})"
    )

    return is_7th_day, daily_record_count


async def save_weekly_summary_with_metadata(
    db,
    user_id: str,
    summary_content: str,
    attendance_count: int
) -> int:
    """주간 요약 저장 (시퀀스 자동 계산)

    Args:
        db: Database 인스턴스
        user_id: 카카오 사용자 ID
        summary_content: 주간 요약 내용
        attendance_count: 현재 attendance_count

    Returns:
        int: 저장된 시퀀스 번호
    """
    sequence_number = attendance_count // 7
    start_attendance_count = (sequence_number - 1) * 7 + 1
    end_attendance_count = sequence_number * 7
    current_date = datetime.now().date().isoformat()

    await db.save_weekly_summary(
        user_id=user_id,
        sequence_number=sequence_number,
        start_daily_count=start_attendance_count,
        end_daily_count=end_attendance_count,
        summary_content=summary_content,
        start_date=None,  # TODO: 일일기록 날짜 추적 추가 후 계산
        end_date=current_date
    )

    logger.info(
        f"[SummaryRepo] 주간요약 저장 완료: "
        f"{sequence_number}번째 ({start_attendance_count}-{end_attendance_count}일차)"
    )

    return sequence_number


async def get_weekly_summary_data(db, user_id: str, limit: int = 7) -> list:
    """주간 요약 생성을 위한 일일 기록 조회

    Args:
        db: Database 인스턴스
        user_id: 카카오 사용자 ID
        limit: 조회할 기록 수 (기본 7개)

    Returns:
        list: 일일 기록 목록
    """
    records = await db.get_daily_records(user_id, limit=limit)
    logger.info(f"[SummaryRepo] 주간 요약용 일일 기록 조회: {len(records)}개")
    return records
