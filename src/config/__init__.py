"""Configuration module

이 모듈은 애플리케이션의 모든 설정 값을 중앙에서 관리합니다.
"""

from datetime import datetime, timezone, timedelta

from .business_config import (
    DAILY_TURNS_THRESHOLD,
    SUMMARY_SUGGESTION_THRESHOLD,
    WEEKLY_SUMMARY_MIN_WEEKDAY_COUNT,
    MAX_CONTEXT_TURNS,
    MAX_ONBOARDING_HISTORY,
)

# 한국 시간대 (KST = UTC+9)
KST = timezone(timedelta(hours=9))


def get_kst_now():
    """한국 시간 기준 현재 datetime 반환 (timezone-aware)"""
    return datetime.now(KST)


__all__ = [
    "DAILY_TURNS_THRESHOLD",
    "SUMMARY_SUGGESTION_THRESHOLD",
    "WEEKLY_SUMMARY_MIN_WEEKDAY_COUNT",
    "MAX_CONTEXT_TURNS",
    "MAX_ONBOARDING_HISTORY",
    "KST",
    "get_kst_now",
]
