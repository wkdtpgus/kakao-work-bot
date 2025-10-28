"""주간 피드백 참고용 응답 생성 (7일 미달 시)"""


def calculate_current_week_day(attendance_count: int) -> int:
    """현재 주차 내 일차 계산

    Args:
        attendance_count: 전체 출석 일수

    Returns:
        int: 주차 내 일차 (1-6, 0은 7로 변환)

    Examples:
        8 → 1, 9 → 2, 14 → 0 → 7, 15 → 1
    """
    remainder = attendance_count % 7
    return remainder if remainder > 0 else 7


def format_partial_weekly_feedback(current_day: int, feedback_text: str) -> str:
    """7일 미달 시 참고용 주간 피드백 응답 포맷팅

    Args:
        current_day: 현재 주차 내 일차 (1-6)
        feedback_text: LLM이 생성한 피드백 본문

    Returns:
        str: 포맷팅된 응답 메시지
    """
    return f"""아직 {current_day}일차예요. 7일차 달성 시 정식 주간요약이 생성되어 저장됩니다.

📌 지금까지의 활동 (참고용)

{feedback_text}

💡 이 내용은 참고용이며, 정식 주간요약이 아닙니다. 일일기록을 7회 완료하면 3분커리어가 자동으로 주간요약을 제안해요!"""


def format_already_processed_message() -> str:
    """7일차 달성했으나 이미 처리된 경우 응답 메시지"""
    return "해당 주간요약은 이미 확인하셨거나 확인 기간이 지났습니다. 다음 7일차에 새로운 주간요약을 확인하실 수 있어요!"


def format_no_record_message() -> str:
    """0일차 (일일기록 시작 전) 응답 메시지"""
    return "아직 일일기록을 시작하지 않으셨어요. 일일기록을 7회 완료하면 주간요약을 확인하실 수 있어요!"
