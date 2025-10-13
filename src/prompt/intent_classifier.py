# 추후 통합 가능성 있음
# ============================================================================
# 1. 일일기록 세션 내 의도 분류 (summary/continue/restart)
# ============================================================================
INTENT_CLASSIFICATION_SYSTEM_PROMPT = "You are an expert at classifying user intent accurately."

INTENT_CLASSIFICATION_USER_PROMPT = """User message: "{message}"

Classify the user's intent into one of the following:
- summary: User explicitly wants to generate/create a daily summary (e.g., "데일리 요약 생성", "데일리 요약 생성해줘", "오늘 요약해줘", "요약 만들어줘", "정리해줘", "요약해줘") OR wants to summarize and finish the current session
- rejection: User is rejecting or canceling the current suggestion
- continue: User wants to continue the conversation
- restart: User wants to start a new daily record session

Response format: Only return one of: summary, rejection, continue, restart"""


# ============================================================================
# 2. 서비스 라우터 의도 분류 (daily_record vs weekly_feedback vs weekly_acceptance vs rejection)
# ============================================================================
SERVICE_ROUTER_SYSTEM_PROMPT = "You are an expert at classifying user intent accurately."

SERVICE_ROUTER_USER_PROMPT = """User message: "{message}"

Classify the user's intent into one of the following:
- daily_record: Daily work, task recording, reflection
- weekly_feedback: User explicitly requests weekly summary
- weekly_acceptance: User accepts/confirms to see weekly summary (positive responses like yes, okay, sure)
- rejection: User rejects suggestion and wants to do something else

Response format: Only return one of: daily_record, weekly_feedback, weekly_acceptance, rejection"""
