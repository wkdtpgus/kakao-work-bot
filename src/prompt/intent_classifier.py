# ============================================================================
# 1. 일일기록 세션 내 의도 분류 (summary/continue/restart)
# ============================================================================
INTENT_CLASSIFICATION_SYSTEM_PROMPT = "You are an expert at classifying user intent accurately."

INTENT_CLASSIFICATION_USER_PROMPT = """User message: "{message}"

Classify the user's intent into one of the following:
- summary: User wants to summarize and finish the current session (e.g., "정리해줘", "요약해줘", "끝", "완료", "네")
- continue: User wants to continue the conversation (e.g., "더 얘기할래", "이것도 말하고 싶어")
- restart: User wants to start a new daily record session (e.g., "다시 시작", "처음부터", "일일기록 시작", "새로")

Response format: Only return one of: summary, continue, restart"""


# ============================================================================
# 2. 서비스 라우터 의도 분류 (daily_record vs weekly_feedback)
# ============================================================================
SERVICE_ROUTER_SYSTEM_PROMPT = "당신은 사용자 의도를 정확히 분류하는 전문가입니다."

SERVICE_ROUTER_USER_PROMPT = """사용자 메시지: "{message}"

위 메시지의 의도를 다음 중 하나로 분류해주세요:
- daily_record: 오늘 한 일, 업무 기록, 회고 등
- weekly_feedback: 주간 피드백, 이번 주 정리, 한 주 돌아보기 등

응답 형식: daily_record 또는 weekly_feedback"""
