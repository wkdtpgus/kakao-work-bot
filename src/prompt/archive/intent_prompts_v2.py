# 추후 통합 가능성 있음
# ============================================================================
# 1. 일일기록 세션 내 의도 분류 (summary/continue/restart)
# ============================================================================
INTENT_CLASSIFICATION_SYSTEM_PROMPT = "You are an expert at classifying user intent accurately."

INTENT_CLASSIFICATION_USER_PROMPT = """User message: "{message}"

Classify the user's intent into one of the following:

DEFAULT BEHAVIOR:
- If unsure: "continue"
- General work conversation: "continue"
- Clarifications during conversation: "continue" (NOT "edit_summary" or "rejection")

1. summary: User wants to generate daily summary OR accepts bot's EXPLICIT summary generation proposal
   - Explicit requests: "정리해줘", "요약해줘"
   - Positive responses ("응", "네", "좋아", "부탁해", "해줘", "okay") ONLY when bot asked: "정리해드릴까요?", "요약해드릴까요?", "내용을 정리해드릴까요?"

2. edit_summary: User wants to modify the JUST CREATED summary with SPECIFIC changes
   - Simple edit requests: "수정해줘", "일일기록 수정해줘"
   - Addition requests: "[내용]도 기록해줘", "~도 넣어줘", "~도 추가해줘", "추가해줘"
   - Removal/correction requests: "[내용] 빠졌어", "이건 틀렸어", "안했어", "~안했어", "~이건 빼줘", "삭제해줘"
   - Key patterns: "빠졌어", "누락", "안 들어갔어", "반영해줘", "수정하고 싶어"
   - Rewrite requests: "다시 작성해", "다시 만들어줘", "다시 정리해줘", "다시 써줘" (ONLY when mentioning modifications/corrections)
   - Example patterns:
     * "수정 내용을 반영해서 다시 작성해" → edit_summary
     * "일일기록 수정해줘" → edit_summary
     * "프롬프트 엔지니어링 안했어. 이건 빼줘" → edit_summary
     * "[내용] 틀렸어" → edit_summary
   - Requires a COMPLETED summary to modify (checked via session flag)

3. no_edit_needed: User indicates NO edits needed AFTER summary was created
   - Bot showed summary and asked about edits: "수정하고 싶은 표현은 없나요?", "디테일은 없나요?"
   - User responds positively: "응", "네", "없어", "괜찮아", "좋아"

4. end_conversation: User wants to END the conversation
   - Clear exit signals: "끝", "종료", "그만", "바이", "bye", "힘들어", "그만할래", "종료할래", "마칠게", "이제 그만"
   - User expresses fatigue or wanting to stop: "피곤해", "힘들다", "그만하고 싶어"

5. rejection: User EXPLICITLY REJECTS a bot's SUMMARY PROPOSAL ONLY
   - CHECK [Previous bot] FIRST: Bot MUST have asked "정리해드릴까요?" or "요약해드릴까요?"
   - ONLY THEN, if user refuses: "아니", "싫어", "나중에", "안 할래"
   - NOT for "그만", "끝", "종료" - these are end_conversation
   - NOT for general negative responses in work conversation (e.g., "없었어", "딱히", "별로")
   - NOT for corrections to summary content (e.g., "~안했어", "~이건 빼줘", "틀렸어") - these are edit_summary
   - NOT for complaints or questions about the conversation (e.g., "왜 멈춰?", "왜 그래?")
   - When in doubt, prefer edit_summary for corrections, or end_conversation for exit intent

6. restart: User wants to start a completely new daily record session (VERY RARE)
   - Explicit restart requests ONLY: "처음부터 다시", "새로 시작", "리셋", "다시 시작하자"
   - Must indicate wanting to discard current session and start fresh
   - NOT for "다시 작성해" (this is edit_summary), "다시 말해줘" (this is continue)

7. continue: User wants to continue daily record conversation (DEFAULT)
   - Work-related conversation, task details, general responses
   - Negative work-related answers DURING conversation: "없었어", "딱히", "별로", "그냥" (when discussing work, NOT correcting summary)
   - Questions or complaints about conversation: "왜?", "왜 멈춰?", "왜 그래?"
   - Positive responses ("응", "좋아") when bot suggests STARTING conversation (NOT summary generation)
   - Conversation clarifications DURING work discussion: "안했어" (when clarifying what work was done, NOT correcting summary)
   - Example: Bot asks "Did you do X?" → User: "안했어" (during work conversation) → continue
   - IMPORTANT: If user corrects/denies AFTER seeing summary → edit_summary, NOT continue

CRITICAL RULES FOR SHORT RESPONSES ("응", "네", "좋아" etc.):
- Check [Previous bot] message context!
- If bot asked to START/CONTINUE conversation ("이야기 나눠볼까요?", "업무에 대해 말해줄래요?") → "continue"
- If bot offered to CREATE SUMMARY ("정리해드릴까요?", "요약해드릴까요?") → "summary"
- If bot asked about EDITING summary ("수정하고 싶은 부분 있나요?") → "no_edit_needed"
- Priority: Check conversation starters FIRST, then summary proposals

INTENT PRIORITY (when ambiguous):
1. end_conversation (explicit exit: "끝", "종료", "그만", "힘들어")
2. restart (explicit restart: "처음부터", "리셋")
3. summary (bot asked summary + user agrees)
4. edit_summary (after summary + user corrects/modifies) - HIGH priority for "수정", "빼줘", "추가해줘"
5. no_edit_needed (after summary + user satisfied)
6. rejection (bot asked summary + user refuses) - VERY LOW priority (prefer edit_summary for corrections)
7. continue (default for everything else)

CRITICAL DISTINCTION - "안했어" / "빼줘":
- If AFTER summary was shown → edit_summary (correcting the summary)
- If DURING work conversation → continue (clarifying what work was done)

Response format: Only return one of: summary, edit_summary, no_edit_needed, end_conversation, rejection, continue, restart"""


# ============================================================================
# 2. 서비스 라우터 의도 분류 (daily_record vs weekly_feedback vs weekly_acceptance vs rejection)
# ============================================================================
SERVICE_ROUTER_SYSTEM_PROMPT = "You are an expert at classifying user intent accurately."

SERVICE_ROUTER_USER_PROMPT = """Conversation context: "{message}"

Classify the user's intent into one of the following:
- daily_record: Daily work, task recording, reflection (DEFAULT for most conversations)
  - Includes positive responses to DAILY-related bot questions (e.g., "지금까지 내용을 정리해드릴까요?" → "응")
- weekly_feedback: User explicitly requests weekly summary
- weekly_acceptance: User accepts/confirms to see WEEKLY summary ONLY
  - ONLY when [Previous bot] explicitly mentioned WEEKLY summary ("주간요약", "주간 피드백")
  - NOT for daily summary acceptance
- rejection: User EXPLICITLY REJECTS a bot's suggestion with clear negative intent (e.g., "아니요", "싫어요", "나중에", "안 할래", "거절")

CRITICAL RULES FOR SHORT POSITIVE RESPONSES ("응", "네", "좋아", etc.):
1. Check [Previous bot] message context!
2. If bot asked about DAILY summary ("지금까지 내용을 정리해드릴까요?", "오늘 내용 정리해드릴까요?") → "daily_record"
3. If bot asked about WEEKLY summary ("주간요약 보여드릴까요?", "주간 피드백 확인하시겠어요?") → "weekly_acceptance"
4. If unclear or no bot proposal → "daily_record" (safer default)

IMPORTANT:
- If unsure, default to "daily_record"
- Only use "rejection" for CLEAR, EXPLICIT refusal responses
- General conversation about work is "daily_record", NOT "rejection"
- Positive responses to daily summary proposals are "daily_record", NOT "weekly_acceptance"

Response format: Only return one of: daily_record, weekly_feedback, weekly_acceptance, rejection"""

SERVICE_ROUTER_USER_PROMPT_WITH_WEEKLY_CONTEXT = """Conversation context: "{message}"

🔔 IMPORTANT CONTEXT: The system has detected that the bot recently proposed/suggested viewing the weekly summary.
The [Previous bot] message above likely contains the weekly summary proposal (e.g., "주간요약도 보여드릴까요?", "주간 피드백 확인하시겠어요?").

Your task: Analyze the [User] message and classify it into one of the following based on whether it responds to the weekly summary proposal:

- weekly_acceptance: User ACCEPTS the weekly summary proposal
  (e.g., "응", "네", "좋아", "그래", "보여줘", "볼래", "okay", "yes", "ㅇㅇ", "ㄱㄱ", "알겠어", "부탁해")
- rejection: User EXPLICITLY REJECTS the weekly summary proposal
  (e.g., "아니", "싫어", "나중에", "안 할래", "거절", "no", "아뇨", "안돼", "싫")
- daily_record: User's message is UNRELATED to the weekly summary proposal (general greeting, small talk, new topic, or changes the subject)
  (e.g., "안녕", "뭐해", "오늘 어땠어", any message that ignores or doesn't address the proposal)

CRITICAL RULES:
1. Check if [Previous bot] message contains weekly summary proposal keywords ("주간요약", "주간 피드백", "weekly")
2. If it does, determine if [User] is responding to it:
   - POSITIVE response → "weekly_acceptance"
   - NEGATIVE response → "rejection"
   - UNRELATED/IGNORING → "daily_record"
3. If [Previous bot] doesn't mention weekly summary, or [User] is clearly talking about something else → "daily_record"
4. Examples of UNRELATED: greetings ("안녕"), off-topic questions ("뭐해?"), new conversation topics
5. When unsure between acceptance and unrelated, prefer "daily_record" (safer default to avoid false positives)

Response format: Only return one of: weekly_acceptance, rejection, daily_record"""
