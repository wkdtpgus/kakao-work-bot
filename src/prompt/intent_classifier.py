# 추후 통합 가능성 있음
# ============================================================================
# 1. 일일기록 세션 내 의도 분류 (summary/continue/restart)
# ============================================================================
INTENT_CLASSIFICATION_SYSTEM_PROMPT = "You are an expert at classifying user intent accurately."

INTENT_CLASSIFICATION_USER_PROMPT = """User message: "{message}"

Classify the user's intent into one of the following:
- summary: User EXPLICITLY wants to generate/create a daily summary OR accepts bot's summary suggestion (e.g., "데일리 요약 생성", "오늘 요약해줘", "정리해줘", "요약해줘", "요약 해줘", "정리 부탁해", "응", "네", "그래", "좋아", "ㅇㅇ", "ㅇㅋ", "okay", "yes")
- edit_summary: User wants to edit/modify/regenerate the JUST CREATED summary with SPECIFIC changes (e.g., "수정해줘", "다시 생성해줘", "재생성", "아니야 이건 빠졌어", "왜 [내용] 반영 안돼?", "추가로 [내용] 넣어줘", "[내용]도 넣어줘", "[내용]도 기록해줘", "[내용]도 포함해줘", "[내용] 안 했는데?", "[내용] 언급한 적 없어", "이건 틀렸어", "이건 아닌데", "[구체적 내용] 빠졌어", "[내용]이 빠졌어", "[구체적 내용] + 수정/반영 요청")
- no_edit_needed: User indicates NO edits are needed after summary (e.g., "없어", "없어요", "괜찮아", "좋아", "알겠어", "응", "네", "그래", "ㅇㅋ", "ㅇㅇ", "ok", "okay")
- end_conversation: User wants to END the conversation (e.g., "끝", "종료", "그만", "이만", "나갈게", "끝낼게", "바이", "bye", "담에 봐", "다음에 봐")
- rejection: User EXPLICITLY REJECTS a bot's suggestion with clear negative intent (e.g., "아니요", "싫어요", "나중에", "안 할래", "거절", "ㄴㄴ")
- restart: User explicitly wants to start a completely new daily record session (e.g., "처음부터 다시", "새로 시작", "리셋")
- continue: User wants to continue the daily record conversation (DEFAULT)

IMPORTANT:
- If unsure, default to "continue"
- **CRITICAL - Context-based classification for short responses ("응", "네", "그래", etc.)**:
  - If bot asked "정리해드릴까요?" / "요약해드릴까요?" → "summary"
  - If bot asked "수정하고 싶은 표현은 없나요?" / "디테일은 없나요?" → "no_edit_needed"
  - Look at the [Previous bot] message to determine context!
- **CRITICAL**: Distinguish between "edit_summary" (needs changes), "no_edit_needed" (satisfied), and "end_conversation" (wants to exit)
  - "edit_summary": User provides SPECIFIC corrections/additions to summary (must mention what to change)
  - "no_edit_needed": Short positive/neutral responses after summary question (satisfied, no changes)
  - "end_conversation": Clear exit/goodbye signals
- Only use "rejection" for CLEAR, EXPLICIT refusal responses to bot's suggestions
- **CRITICAL**: Corrections/negations during ongoing conversation ("안했어", "선택 안했다니까", "그거 아니야") are "continue", NOT "edit_summary" or "rejection"
  - These are part of the conversation flow where user is clarifying what they actually did
  - Only classify as "edit_summary" if there's a COMPLETED summary to modify
- General work-related conversation is "continue", NOT "rejection"
- **🚨 edit_summary priority**: If user requests to ADD/INCLUDE/RECORD specific content to summary (e.g., "[내용]도 기록해줘", "[내용]도 넣어줘", "[내용]도 포함해줘", "[내용] 빠졌어"), it's "edit_summary" even if wording is casual
- **🚨 Key patterns for edit_summary**: "빠졌어", "누락", "안 들어갔어", "~도 넣어줘", "~도 기록해줘", "~도 포함해줘", "추가해줘", "반영해줘"

Response format: Only return one of: summary, edit_summary, no_edit_needed, end_conversation, rejection, continue, restart"""


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
