"""Database module - DB 접근 및 복합 쿼리"""

from .database import Database

# Schemas
from .schemas import (
    UserSchema,
    ConversationStateSchema,
    ConversationMessageSchema,
    AIConversationSchema,
    DailyRecordSchema,
    WeeklySummarySchema
)

# User Repository
from .user_repository import (
    get_user_with_context,
    check_and_reset_daily_count,
    increment_counts_with_check,
    save_onboarding_metadata,
    complete_onboarding,
    get_onboarding_history
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

# Summary Repository
from .summary_repository import (
    save_daily_summary_with_checks,
    save_weekly_summary_with_metadata,
    get_weekly_summary_data
)

__all__ = [
    # Database class
    "Database",

    # Schemas
    "UserSchema",
    "ConversationStateSchema",
    "ConversationMessageSchema",
    "AIConversationSchema",
    "DailyRecordSchema",
    "WeeklySummarySchema",

    # User Repository
    "get_user_with_context",
    "check_and_reset_daily_count",
    "increment_counts_with_check",
    "save_onboarding_metadata",
    "complete_onboarding",
    "get_onboarding_history",

    # Conversation Repository
    "get_today_conversations",
    "get_weekly_summary_flag",
    "clear_weekly_summary_flag",
    "set_weekly_summary_flag",
    "update_daily_session_data",
    "handle_rejection_flag",

    # Summary Repository
    "save_daily_summary_with_checks",
    "save_weekly_summary_with_metadata",
    "get_weekly_summary_data",
]
