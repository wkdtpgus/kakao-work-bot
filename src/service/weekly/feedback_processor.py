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


async def handle_official_weekly_feedback(
    db,
    user_id: str,
    metadata,
    llm
) -> WeeklyFeedbackResponse:
    """정식 주간 피드백 생성 (7일차 자동 트리거)

    Args:
        db: Database 인스턴스
        user_id: 사용자 ID
        metadata: UserMetadata 객체
        llm: LLM 인스턴스

    Returns:
        WeeklyFeedbackResponse: 처리 결과
    """
    from ...database import prepare_weekly_feedback_data
    from .feedback_generator import generate_weekly_feedback

    logger.info(f"[WeeklyHandler] 정식 주간 피드백 생성")

    # user_data 캐시 전달 (중복 DB 쿼리 방지)
    user_data = {
        "name": metadata.name,
        "job_title": metadata.job_title,
        "career_goal": metadata.career_goal
    }

    input_data = await prepare_weekly_feedback_data(db, user_id, user_data=user_data)
    output = await generate_weekly_feedback(input_data, llm)
    weekly_summary = output.feedback_text

    return WeeklyFeedbackResponse(
        ai_response=weekly_summary,
        is_summary=True,
        summary_type='weekly',
        should_clear_flag=True
    )


async def handle_no_record_yet(
) -> WeeklyFeedbackResponse:
    """일일기록 시작 전 (0일차)

    Returns:
        WeeklyFeedbackResponse: 처리 결과
    """
    from .fallback_handler import format_no_record_message

    logger.info(f"[WeeklyHandler] 0일차 (일일기록 시작 전)")

    return WeeklyFeedbackResponse(
        ai_response=format_no_record_message(),
        is_summary=False
    )


async def handle_partial_weekly_feedback(
    db,
    user_id: str,
    metadata,
    current_count: int,
    llm
) -> WeeklyFeedbackResponse:
    """참고용 주간 피드백 생성 (1~6일차)

    Args:
        db: Database 인스턴스
        user_id: 사용자 ID
        metadata: UserMetadata 객체
        current_count: 현재 출석 일수
        llm: LLM 인스턴스

    Returns:
        WeeklyFeedbackResponse: 처리 결과
    """
    from ...database import prepare_weekly_feedback_data
    from .feedback_generator import generate_weekly_feedback
    from .fallback_handler import calculate_current_week_day, format_partial_weekly_feedback

    # 현재 주차 내 일차 계산
    current_day_in_week = calculate_current_week_day(current_count)
    logger.info(f"[WeeklyHandler] 7일 미달 (현재 {current_day_in_week}일차) → 참고용 피드백 제공")

    # user_data 캐시 전달
    user_data = {
        "name": metadata.name,
        "job_title": metadata.job_title,
        "career_goal": metadata.career_goal
    }

    # 임시 피드백 생성
    input_data = await prepare_weekly_feedback_data(db, user_id, user_data=user_data)
    output = await generate_weekly_feedback(input_data, llm)
    partial_feedback = output.feedback_text

    # 헬퍼 함수로 응답 포맷팅
    ai_response = format_partial_weekly_feedback(current_day_in_week, partial_feedback)

    return WeeklyFeedbackResponse(
        ai_response=ai_response,
        is_summary=True,
        summary_type='daily'  # 참고용은 daily로 저장
    )


async def process_weekly_feedback(
    db,
    user_id: str,
    metadata,
    is_ready: bool,
    stored_attendance_count: Optional[int],
    current_count: int,
    llm
) -> WeeklyFeedbackResponse:
    """주간 피드백 처리 메인 로직

    Args:
        db: Database 인스턴스
        user_id: 사용자 ID
        metadata: UserMetadata 객체
        is_ready: 주간 요약 플래그 여부
        stored_attendance_count: 플래그에 저장된 출석 일수
        current_count: 현재 출석 일수
        llm: LLM 인스턴스

    Returns:
        WeeklyFeedbackResponse: 처리 결과
    """
    # 1. 7일차 자동 트리거 (플래그 O + 출석 일수 저장됨)
    if is_ready and stored_attendance_count:
        logger.info(f"[WeeklyHandler] 7일차 주간요약 생성 (attendance_count={stored_attendance_count})")
        return await handle_official_weekly_feedback(db, user_id, metadata, llm)

    # 2. 수동 요청 - 0일차: 일일기록 시작 전
    if current_count == 0:
        return await handle_no_record_yet()

    # 3. 수동 요청 - 1~6일차: 참고용 피드백 제공
    if current_count % 7 != 0:
        return await handle_partial_weekly_feedback(db, user_id, metadata, current_count, llm)

    # 4. 수동 요청 - 7일차 이후: 정식 주간요약 제공 (플래그 없어도 OK)
    logger.info(f"[WeeklyHandler] 7일차 이후 수동 요청 → 정식 주간요약 제공")
    return await handle_official_weekly_feedback(db, user_id, metadata, llm)
