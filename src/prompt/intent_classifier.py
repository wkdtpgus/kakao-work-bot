"""사용자 의도 분류 프롬프트"""

INTENT_CLASSIFICATION_SYSTEM_PROMPT = "You are an expert at classifying user intent accurately."

INTENT_CLASSIFICATION_USER_PROMPT = """User message: "{message}"

Classify the user's intent into one of the following:
- summary: User wants to summarize and finish the current session (e.g., "정리해줘", "요약해줘", "끝", "완료", "네")
- continue: User wants to continue the conversation (e.g., "더 얘기할래", "이것도 말하고 싶어")
- restart: User wants to start a new daily record session (e.g., "다시 시작", "처음부터", "일일기록 시작", "새로")

Response format: Only return one of: summary, continue, restart"""
