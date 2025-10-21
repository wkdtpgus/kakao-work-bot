# 추후 통합 가능성 있음
# ============================================================================
# 1. 일일기록 세션 내 의도 분류 (summary/continue/restart)
# ============================================================================
INTENT_CLASSIFICATION_SYSTEM_PROMPT = "You are an expert at classifying user intent accurately."

INTENT_CLASSIFICATION_USER_PROMPT = """User message: "{message}"

Classify the user's intent into one of the following:
- summary: User wants to generate/create a daily summary OR accepts bot's summary suggestion (e.g., "데일리 요약 생성", "오늘 요약해줘", "정리해줘", "요약해줘", "응", "네", "그래", "좋아", "ㅇㅇ", "ㅇㅋ", "yes", "okay")
- edit_summary: User wants to edit/modify/regenerate the JUST CREATED summary OR complains about summary accuracy (e.g., "수정해줘", "다시 생성해줘", "아니야 이건 빠졌어", "왜 [내용] 반영 안돼?", "추가로 [내용] 넣어줘", "[내용] 안 했는데?", "[내용] 언급한 적 없어", "이건 틀렸어", "이건 아닌데")
- rejection: User EXPLICITLY REJECTS a bot's suggestion with clear negative intent (e.g., "아니요", "싫어요", "나중에", "안 할래", "거절", "ㄴㄴ")
- restart: User explicitly wants to start a completely new daily record session (e.g., "처음부터 다시", "새로 시작", "리셋")
- continue: User wants to continue the daily record conversation (DEFAULT)

IMPORTANT:
- If unsure, default to "continue"
- "응", "네", "그래", "좋아" 등 긍정 응답은 "summary"로 분류 (봇이 요약 제안했을 가능성 높음)
- Only use "rejection" for CLEAR, EXPLICIT refusal responses to bot's suggestions
- "edit_summary" includes ANY complaint or correction about the summary content (e.g., factual errors, missing info, hallucinations)
- **CRITICAL**: Corrections/negations during ongoing conversation ("안했어", "선택 안했다니까", "그거 아니야") are "continue", NOT "edit_summary" or "rejection"
  - These are part of the conversation flow where user is clarifying what they actually did
  - Only classify as "edit_summary" if there's a COMPLETED summary to modify
- General work-related conversation is "continue", NOT "rejection"

Response format: Only return one of: summary, edit_summary, rejection, continue, restart"""


# ============================================================================
# 2. 서비스 라우터 의도 분류 (daily_record vs weekly_feedback vs weekly_acceptance vs rejection)
# ============================================================================
SERVICE_ROUTER_SYSTEM_PROMPT = "You are an expert at classifying user intent accurately."

SERVICE_ROUTER_USER_PROMPT = """User message: "{message}"

Classify the user's intent into one of the following:
- daily_record: Daily work, task recording, reflection (DEFAULT for most conversations)
- weekly_feedback: User explicitly requests weekly summary
- weekly_acceptance: User accepts/confirms to see weekly summary (positive responses like yes, okay, sure)
- rejection: User EXPLICITLY REJECTS a bot's suggestion with clear negative intent (e.g., "아니요", "싫어요", "나중에", "안 할래", "거절")

IMPORTANT:
- If unsure, default to "daily_record"
- Only use "rejection" for CLEAR, EXPLICIT refusal responses
- General conversation about work is "daily_record", NOT "rejection"

Response format: Only return one of: daily_record, weekly_feedback, weekly_acceptance, rejection"""
