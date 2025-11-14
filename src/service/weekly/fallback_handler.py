"""주간 피드백 메시지 포맷팅 (평일 기반)"""


def format_no_record_message() -> str:
    """일일기록 시작 전 응답 메시지"""
    return "아직 일일기록을 시작하지 않으셨어요. 평일에 일일기록을 작성하고 주말에 주간요약을 확인해보세요!"


def format_insufficient_weekday_message(weekday_count: int) -> str:
    """평일 작성 일수 부족 시 응답 메시지

    Args:
        weekday_count: 현재 주 평일 작성 일수

    Returns:
        str: 포맷팅된 응답 메시지
    """
    return f"""이번 주 평일 작성이 {weekday_count}일이에요. 주간요약은 평일 2일 이상 작성 후 주말에 제공됩니다.

💡 평일(월~금)에 일일기록을 작성하고 주말에 주간요약을 받아보세요!"""
