"""Database module - DB 접근 및 복합 쿼리"""

from .database import Database

# Schemas - REMOVED (dict 사용으로 변경)

# User Repository
from .user_repository import (
    get_user_with_context,
    check_and_reset_daily_count,
    increment_counts_with_check,
    save_onboarding_metadata,
    complete_onboarding,
    increment_weekday_record_count,
    get_weekday_record_count
)

# Conversation Repository
from .conversation_repository import (
    get_today_conversations,
    get_weekly_summary_flag,
    clear_weekly_summary_flag,
    set_weekly_summary_flag,
    update_daily_session_data,
    handle_rejection_flag
)

# Summary Repository (V2 스키마)
from .summary_repository import (
    save_daily_summary_v2,
    save_weekly_summary_v2,
    get_daily_summaries_for_weekly_v2,
    get_all_summaries_v2,
    check_weekly_summary_ready,
    prepare_daily_summary_data,
    prepare_weekly_feedback_data
)

__all__ = [
    # Database class
    "Database",

    # User Repository
    "get_user_with_context",
    "check_and_reset_daily_count",
    "increment_counts_with_check",
    "save_onboarding_metadata",
    "complete_onboarding",
    "increment_weekday_record_count",
    "get_weekday_record_count",

    # Conversation Repository
    "get_today_conversations",
    "get_weekly_summary_flag",
    "clear_weekly_summary_flag",
    "set_weekly_summary_flag",
    "update_daily_session_data",
    "handle_rejection_flag",

    # Summary Repository (V2)
    "save_daily_summary_v2",
    "save_weekly_summary_v2",
    "get_daily_summaries_for_weekly_v2",
    "get_all_summaries_v2",
    "check_weekly_summary_ready",
    "prepare_daily_summary_data",
    "prepare_weekly_feedback_data",
]
