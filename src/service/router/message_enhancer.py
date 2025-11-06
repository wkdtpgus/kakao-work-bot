"""의도 분류를 위한 메시지 컨텍스트 강화 유틸리티

Service Router에서 사용자 의도를 정확히 파악하기 위해
직전 봇 메시지를 추출하는 기능 제공
"""

from typing import Optional, List, Dict


def extract_last_bot_message(cached_today_turns: List[Dict[str, str]]) -> Optional[str]:
    """
    최근 대화 턴에서 마지막 봇 메시지를 추출

    Args:
        cached_today_turns: [{"user_message": "...", "ai_message": "..."}, ...] 형식
                           (turn_index 내림차순 정렬 - 최신이 앞에)

    Returns:
        마지막 AI 메시지 또는 None

    Example:
        >>> turns = [{"user_message": "안녕", "ai_message": "안녕하세요!"}]
        >>> extract_last_bot_message(turns)
        "안녕하세요!"
    """
    if not cached_today_turns:
        return None

    # 최신 턴이 첫 번째 (turn_index 내림차순)
    last_turn = cached_today_turns[0] if cached_today_turns else None
    if last_turn and last_turn.get("ai_message"):
        return last_turn["ai_message"]

    return None
