# 추후 통합 가능성 있음
# ============================================================================
# 1. 일일기록 세션 내 의도 분류 (summary/continue/restart)
# ============================================================================
INTENT_CLASSIFICATION_SYSTEM_PROMPT = "You are an expert at classifying user intent accurately."

INTENT_CLASSIFICATION_USER_PROMPT = """User message: "{message}"

Classify the user's intent (return ONE word only):

**DEFAULT: If unsure → "continue"**

**CRITICAL: Short responses ("응", "네", "좋아", "okay", "괜찮아") - CHECK [Previous bot] context:**
- If bot asked "정리해드릴까요?" / "요약해드릴까요?" / "내용을 정리해드릴까요?" → summary
- If bot asked "수정하고 싶은 표현은 없나요?" / "디테일은 없나요?" → no_edit_needed
- If bot asked to START conversation ("이야기 나눠볼까요?", "업무에 대해") → continue
- **If NO [Previous bot] context or NO clear question → continue (DEFAULT)**

**1. summary** - User wants daily summary
- Explicit: "정리", "요약" keywords (e.g., "정리해줘", "요약해줘", "정리 부탁해", "정리ㄱㄱ")
- Acceptance: "응/네/좋아/부탁해/오케이/ㅇㅇ/ㄱㄱ/ㅇㅋ" ONLY when bot asked "정리해드릴까요?"

**2. edit_summary** - Modify completed summary (HIGH PRIORITY)
- **Check context first**: ONLY if context contains "요약:", "📝", "커리어 메모"
- Edit requests: "수정해줘", "일일기록 수정해줘"
- Add content: "추가해줘", "넣어줘", "~도 기록해줘", "~도 했어" (AFTER summary)
- Remove: "빼줘", "삭제해줘"
- Corrections: "틀렸어", "잘못됐어", "안했어", "하지 않았어", "누락", "빠져있어"
- Rewrite: "다시 작성해", "다시 정리해", "반영해줘"
- "안했어" AFTER summary shown (e.g., context contains "요약:", "📝")

**3. no_edit_needed** - Summary is good
- "응/네/없어/완벽해/잘됐어" after bot asked "수정하고 싶은 표현은 없나요?" or "디테일은 없나요?"
- NOT "괜찮아" after summary proposal (that's rejection)

**4. end_conversation** - Exit conversation
- Keywords: "끝", "종료", "그만", "바이", "bye", "ㅂㅂ", "힘들어", "피곤해", "지쳤어"
- Phrases: "그만할래", "종료할래", "마칠게", "이제 그만", "여기까지", "끝낼게", "잘자", "굿밤"

**5. rejection** - Refuse summary proposal (LOW PRIORITY)
- "아니/싫어/나중에/안 할래/됐어/괜찮아/별로" ONLY after bot asked "정리해드릴까요?"
- NOT for corrections (use edit_summary)

**6. restart** - Start new session (RARE)
- Onboarding: "온보딩 다시", "온보딩 초기화", "온보딩 재시작", "프로필 재설정"
- General: "처음부터 다시", "새로 시작", "리셋", "다시 시작하자", "다시 시작할게"
- NOT "다시 작성해" (edit_summary) or "다시 해볼게" in work context (continue)

**7. continue** - Work conversation (DEFAULT)
- Work content, task details, general responses
- "~했어" without summary context
- Negative answers: "없었어", "딱히", "별로" (in work context)

**Context distinction:**
- AFTER summary (context has "요약:", "📝", "커리어 메모") + correction/addition → edit_summary
- DURING conversation (no summary context) → continue

Priority: end_conversation > restart > summary > edit_summary > no_edit_needed > rejection > continue

Response format: summary|edit_summary|no_edit_needed|end_conversation|rejection|continue|restart"""


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
