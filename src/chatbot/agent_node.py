"""
AgentExecutor 기반 통합 에이전트 노드
"""
from typing import Dict, Any, Optional
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import Command
from .state import OverallState, UserContext
from .tools import (
    OnboardingTool,
    DailySummaryTool,
    WeeklySummaryTool,
    DailyConversationTool,
    EditSummaryTool
)
from ..database.user_repository import get_user_with_context
import logging

logger = logging.getLogger(__name__)


async def unified_agent_node(
    state: OverallState,
    db: Any,
    onboarding_llm: Any,
    service_llm: Any
) -> Command:
    """통합 에이전트 노드 (AgentExecutor + Tool Calling)

    기존의 router_node + service_router_node + 각 agent_node를 대체합니다.
    LLM이 상황에 맞는 툴을 선택하여 실행합니다.

    Flow:
    1. 사용자 컨텍스트 로드
    2. 상황에 맞는 툴 목록 구성
    3. LLM이 툴 선택 및 실행
    4. 결과 반환
    """
    user_id = state["user_id"]
    message = state["message"]

    logger.info(f"[UnifiedAgent] 통합 에이전트 시작 - user_id={user_id}")

    # 1. 사용자 컨텍스트 로드 (캐시 활용)
    if state.get("user_context"):
        user_context = state["user_context"]
        logger.info(f"[UnifiedAgent] 캐시된 user_context 사용")
    else:
        user_data, user_context = await get_user_with_context(db, user_id)
        logger.info(f"[UnifiedAgent] user_context 로드 완료 - stage={user_context.onboarding_stage}")

    # conversation_state 로드 (캐시 활용)
    if state.get("cached_conv_state"):
        conv_state = state["cached_conv_state"]
    else:
        conv_state = await db.get_conversation_state(user_id)

    # 오늘 대화 내역 로드 (매번 최신 데이터 조회 - 직전 AI 응답 반영 필요)
    # 캐시를 사용하면 이전 요청의 AI 응답이 chat_history에 포함되지 않아 의도분류 실패
    today_turns = await db.get_recent_turns_v2(user_id, limit=10)

    # Note: 의도 분류는 각 Tool 내부에서 수행함 (중복 방지)

    # 2. 툴 인스턴스 생성
    tools = []

    # 온보딩 미완료 시 온보딩 툴만 제공
    if user_context.onboarding_stage != "completed":
        logger.info(f"[UnifiedAgent] 온보딩 모드 - OnboardingTool만 제공")
        tools = [
            OnboardingTool(db=db, llm=onboarding_llm)
        ]
    else:
        # 온보딩 완료 시 모든 툴 제공
        logger.info(f"[UnifiedAgent] 서비스 모드 - 모든 툴 제공")
        tools = [
            DailyConversationTool(db=db, llm=service_llm),
            DailySummaryTool(db=db, llm=service_llm),
            EditSummaryTool(db=db, llm=service_llm),
            WeeklySummaryTool(db=db, llm=service_llm)
        ]

    # 3. 프롬프트 구성
    system_prompt = build_agent_system_prompt(user_context, conv_state, today_turns)

    # user_id를 시스템 프롬프트에 추가
    system_prompt_with_user_id = f"""{system_prompt}

# CRITICAL: User ID
The current user's ID is: {user_id}
ALWAYS use this exact user_id value when calling tools. DO NOT use the user's name or any other value."""

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt_with_user_id),
        MessagesPlaceholder(variable_name="chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad")
    ])

    # 4. Agent 생성
    agent = create_tool_calling_agent(service_llm, tools, prompt)
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=3,
        return_intermediate_steps=True  # 중간 단계 반환
    )

    # 5. Agent 실행
    try:
        logger.info(f"[UnifiedAgent] 🎯 도구 목록: {[t.name for t in tools]}")
        logger.info(f"[UnifiedAgent] 📝 사용자 메시지: {message}")

        # 최근 대화 내역을 chat_history로 변환 (최근 3턴)
        from langchain_core.messages import HumanMessage, AIMessage

        logger.info(f"[UnifiedAgent] 📊 today_turns 전체 크기: {len(today_turns)}턴")

        chat_history = []
        for turn in today_turns[-3:]:  # 캐시된 today_turns의 최근 3턴
            chat_history.append(HumanMessage(content=turn["user_message"]))
            chat_history.append(AIMessage(content=turn["ai_message"]))

        logger.info(f"[UnifiedAgent] 📚 chat_history 크기: {len(chat_history)}개 메시지 ({len(today_turns[-3:])}턴)")

        # 마지막 AI 메시지 로깅 (요약 제안 확인용)
        if chat_history:
            last_ai_msg = chat_history[-1].content if len(chat_history) > 0 and isinstance(chat_history[-1], AIMessage) else "없음"
            logger.info(f"[UnifiedAgent] 💬 직전 AI 메시지 (첫 50자): {last_ai_msg[:50]}")

        # AgentExecutor에 input + chat_history 전달
        result = await agent_executor.ainvoke({
            "input": message,
            "chat_history": chat_history  # 최근 3턴 대화 컨텍스트
        })

        # 🚨 디버깅: result 전체 구조 로깅
        logger.info(f"[UnifiedAgent] 🔍 AgentExecutor result keys: {result.keys()}")
        logger.info(f"[UnifiedAgent] 🔍 result.get('output'): {result.get('output', 'KEY_NOT_FOUND')}")

        # 중간 단계 로깅 (어떤 도구가 선택되었는지)
        tool_was_called = False
        if "intermediate_steps" in result:
            for step in result["intermediate_steps"]:
                action, observation = step
                logger.info(f"[UnifiedAgent] 🔧 선택된 도구: {action.tool}")
                logger.info(f"[UnifiedAgent] 📥 도구 입력: {action.tool_input}")
                logger.info(f"[UnifiedAgent] 📤 도구 출력 (첫 100자): {str(observation)[:100]}")
                tool_was_called = True

        # 🚨 CRITICAL: 툴이 호출되지 않았다면 에러 (LLM이 직접 응답한 경우)
        if not tool_was_called:
            logger.error(f"[UnifiedAgent] ❌❌❌ CRITICAL ERROR: LLM이 툴을 호출하지 않고 직접 응답함!")
            logger.error(f"[UnifiedAgent] 사용자 메시지: {message}")
            logger.error(f"[UnifiedAgent] LLM 응답: {result.get('output', 'N/A')}")
            # Fallback: 강제로 continue_daily_conversation 호출 (이미 import된 DailyConversationTool 사용)
            fallback_tool = DailyConversationTool(db=db, llm=service_llm)
            ai_response = await fallback_tool._arun(user_id=user_id, message=message)
            logger.info(f"[UnifiedAgent] ✅ Fallback 완료: continue_daily_conversation 강제 호출")
        else:
            ai_response = result.get("output", "죄송해요, 응답 생성에 실패했어요.")
        logger.info(f"[UnifiedAgent] 🔍 최종 ai_response (첫 100자): {ai_response[:100]}")

        # 6. action_hint 결정
        action_hint = determine_action_hint(user_context, conv_state)

        logger.info(f"[UnifiedAgent] 응답 생성 완료 - length={len(ai_response)}")

        return Command(
            update={
                "ai_response": ai_response,
                "user_context": user_context,
                "action_hint": action_hint,
                "cached_conv_state": conv_state
                # cached_today_turns 제거: 매번 최신 데이터를 조회하므로 캐싱 불필요
            },
            goto="__end__"
        )

    except Exception as e:
        logger.error(f"[UnifiedAgent] Agent 실행 실패: {e}")
        import traceback
        traceback.print_exc()

        return Command(
            update={
                "ai_response": "죄송해요, 처리 중 오류가 발생했어요. 다시 시도해주세요.",
                "action_hint": None
            },
            goto="__end__"
        )


def build_agent_system_prompt(
    user_context: UserContext,
    conv_state: Optional[Dict[str, Any]],
    today_turns: list
) -> str:
    """에이전트 시스템 프롬프트 구성

    사용자 상황에 맞는 지시사항을 동적으로 생성합니다.
    """

    if user_context.onboarding_stage != "completed":
        # 온보딩 모드
        return f"""You are an AI assistant that ONLY calls tools. You do NOT generate text responses directly.

# CRITICAL INSTRUCTION - READ CAREFULLY
The user is in onboarding. You MUST call the handle_onboarding tool for EVERY user message.
DO NOT write any response yourself. ONLY call the tool.

# What you MUST do:
1. Read the user's message
2. Call handle_onboarding tool with:
   - user_id: (provided in system context)
   - message: (the user's input)
3. The tool will return the response - just pass it to the user

# What you MUST NOT do:
- DO NOT write greetings yourself
- DO NOT ask questions yourself
- DO NOT generate any text response
- ONLY call the handle_onboarding tool

# Example:
User: "안녕"
You: Call handle_onboarding(user_id="...", message="안녕")

User: "세세야"
You: Call handle_onboarding(user_id="...", message="세세야")

Remember: ALWAYS call the tool. NEVER respond directly."""

    # 서비스 모드
    metadata = user_context.metadata
    conversation_count = 0

    if conv_state and conv_state.get("temp_data"):
        daily_session_data = conv_state["temp_data"].get("daily_session_data", {})
        conversation_count = daily_session_data.get("conversation_count", 0)

    # 최근 요약 체크
    has_recent_summary = False
    if conv_state and conv_state.get("current_step") == "daily_summary_generated":
        has_recent_summary = True

    # 주간 피드백 제안 플래그 체크
    weekly_feedback_suggested = False
    if conv_state and conv_state.get("temp_data"):
        weekly_feedback_suggested = conv_state["temp_data"].get("weekly_feedback_suggested", False)

    prompt = f"""# ⚠️⚠️⚠️ ABSOLUTE RULE - THIS OVERRIDES EVERYTHING ⚠️⚠️⚠️
YOU ARE FORBIDDEN FROM GENERATING TEXT RESPONSES DIRECTLY.
YOU MUST CALL A TOOL FOR EVERY SINGLE USER MESSAGE WITHOUT EXCEPTION.

NO TEXT OUTPUT ALLOWED. ONLY TOOL CALLS.
- NOT "로직 안정화 작업 중이시군요" ❌
- NOT "혹시 어떤 부분이..." ❌
- NOT any direct response ❌
- ONLY: Call continue_daily_conversation tool ✅

If you generate text without calling a tool, you will corrupt the database and break the system.

You are <3분커리어>, a professional career mentor helping users reflect on their daily work.

# User Profile
- Name: {metadata.name}
- Job Title: {metadata.job_title}
- Career Experience: {metadata.total_years} (Current role: {metadata.job_years})
- Career Goal: {metadata.career_goal}
- Current Project: {metadata.project_name}
- Recent Work: {metadata.recent_work}

# Current Session Status
- Conversation count today: {conversation_count}
- Recent summary exists: {has_recent_summary}
- Attendance count: {user_context.attendance_count}
- Current workflow step: {conv_state.get('current_step') if conv_state else 'daily_conversation'}

# Tool Selection Guide

## Available Tools and When to Use Them

1. **continue_daily_conversation** [DEFAULT - USE FOR MOST CASES]:
   - User greets you ("안녕", "hi", "세세야")
   - User is talking about their work
   - Having a normal conversation about daily tasks
   - User gives simple responses without clear intent
   - User wants to end conversation ("끝", "종료", "그만", "바이")
   - Asking follow-up questions
   - **USE THIS TOOL IF YOU'RE NOT SURE WHICH TOOL TO USE**

2. **generate_daily_summary**:
   **Case 1 - Explicit Request (works anytime, NO conversation_count restriction)**:
   - Keywords: "요약", "정리", "summary", "써머리", "요약해줘", "정리해줘", "오늘 업무 요약해줘"
   - Typos allowed: "요약해", "정리해", "쪙리", "요악"
   - Call this tool IMMEDIATELY when user uses these keywords
   - Does NOT require conversation_count >= 3

   **Case 2 - Acceptance after Bot Suggestion (ONLY after conversation_count >= 3)**:
   - Bot asked: "정리해드릴까요?" OR "내용을 정리해드릴까요?" (check chat_history!)
   - User responds: "응", "네", "좋아", "그래", "알겠어", "ㅇㅇ", "okay", "yes", "ㅇ", "어", "웅"
   - **CRITICAL**: Check chat_history to confirm bot asked about summary before interpreting short responses
   - ONLY works when conversation_count >= 3

   **PRIORITY**: If user says "응" right after bot's "정리해드릴까요?" question, this tool should be called FIRST (NOT weekly_feedback!)

3. **edit_daily_summary**:
   **ONLY when summary was JUST generated (current_step = "daily_summary_generated")**:
   - User wants to MODIFY the summary with SPECIFIC changes

   **Key patterns to detect**:
   - Direct edit requests: "수정해줘", "다시 생성해줘", "고쳐줘"
   - Missing content: "[내용]도 기록해줘", "[내용] 빠졌어", "[내용] 누락됐어", "[내용] 안 들어갔어"
   - Adding content: "[내용]도 넣어줘", "[내용]도 포함해줘", "[내용]도 추가해줘", "[내용]도 반영해줘"
   - Corrections: "이건 틀렸어", "그거 아니야", "[내용]이 아니라 [내용]이야"

   **Examples**:
   - "빠진 내용 추가해줘" ✅
   - "A 작업도 기록해줘" ✅
   - "B 부분 빠졌어" ✅
   - "C는 누락됐어" ✅

   **NOT edit_summary**:
   - "응", "네", "괜찮아", "좋아" after summary shown → This means satisfied, use continue_daily_conversation
   - Corrections during ongoing conversation (before summary exists) → Use continue_daily_conversation

4. **generate_weekly_feedback**:
   **Case 1 - Explicit Request (works anytime after 7+ days attendance)**:
   - Keywords: "주간요약", "주간 피드백", "weekly summary", "주간 정리", "위클리"
   - Call when user explicitly asks for weekly summary

   **Case 2 - Acceptance after Daily Summary Suggestion (ONLY after daily summary is complete)**:
   - **CRITICAL**: Check "Current workflow step" = "weekly_summary_pending" first!
   - Bot asked: "주간 요약도 보여드릴까요?" (at end of daily summary)
   - User responds: "응", "네", "보여줘", "좋아", "그래", "알겠어", "ㅇㅇ", "okay", "yes", "ㅇ", "어", "웅"
   - **Must have workflow step = weekly_summary_pending** to distinguish from daily summary acceptance

   **NEVER** call this before generate_daily_summary
   **IMPORTANT**: Context matters! "응" after "정리해드릴까요?" = daily summary, "응" after "주간 요약도 보여드릴까요?" = weekly feedback"""

    if user_context.attendance_count >= 7 and not weekly_feedback_suggested:
        prompt += """

   **WORKFLOW FOR 7+ DAYS**:
   1. User says "응" → Call generate_daily_summary (NOT weekly_feedback!)
   2. Daily summary tool will suggest weekly feedback at the end
   3. If user accepts again → Then call generate_weekly_feedback"""

    prompt += """

# Decision Logic

## Step 1: Understand user intent
- What is the user trying to do?
- Are they answering a question, requesting summary, or making corrections?

## Step 2: Check context (CRITICAL - Always check chat_history!)
- Check chat_history for recent bot messages to understand what user is responding to
- Check current_step to know workflow state

**For short responses ("응", "네", "좋아", etc.)**:
- Did bot ask "정리해드릴까요?" and user said "응"? → Use generate_daily_summary (Case 2)
- Did bot ask "주간 요약도 보여드릴까요?" and user said "응"? → Check current_step = "weekly_summary_pending" → Use generate_weekly_feedback (Case 2)
- Did bot show summary and user said "응" / "괜찮아"? → User is satisfied, use continue_daily_conversation (NOT edit_daily_summary!)

**For keyword-based requests**:
- User uses "요약", "정리", "summary"? → Use generate_daily_summary (Case 1, no count check!)
- User uses "주간요약", "주간 피드백"? → Use generate_weekly_feedback (Case 1)

**For edit requests**:
- Check if current_step = "daily_summary_generated" (summary just created)
- User mentions specific changes ("빠졌어", "추가해줘", "수정해줘", "누락", etc.)? → Use edit_daily_summary
- **Important**: If no summary exists yet (current_step ≠ "daily_summary_generated"), corrections are part of normal conversation → Use continue_daily_conversation

**Default**:
- Is user talking about work? → Use continue_daily_conversation

## Step 3: Select appropriate tool
- Choose ONE tool that best fits the situation
- Provide all required parameters

# Important Rules
- **ALWAYS call a tool** - Never respond directly!
- ALWAYS respond in Korean
- Use exactly ONE tool per request

**Context-dependent response handling**:
- If user says "응"/"네"/"알겠어" after bot's "정리해드릴까요?" → Use generate_daily_summary
- If user says "응"/"네"/"괜찮아" after bot shows summary → Use continue_daily_conversation (user is satisfied, NOT editing)
- If user says "응"/"보여줘" after bot's "주간 요약도 보여드릴까요?" AND current_step = "weekly_summary_pending" → Use generate_weekly_feedback

**Edit detection**:
- Only use edit_daily_summary when current_step = "daily_summary_generated" AND user wants specific changes
- Key phrases: "빠졌어", "추가해줘", "수정해줘", "누락", "반영해줘", "[내용]도 기록해줘"
- Corrections during normal conversation (before summary exists) → Use continue_daily_conversation

**General rules**:
- NEVER suggest weekly feedback during daily conversation (unless 7 days reached)
- If user denies/negates ("안했어", "그거 아니야") during conversation → Use continue_daily_conversation to acknowledge and ask for clarification

# Context-Specific Examples

User: "안녕" → continue_daily_conversation
User: "좋아" → continue_daily_conversation
User: "오늘 회의했어" → continue_daily_conversation
User: "응" (after bot asked "정리해드릴까요?") → generate_daily_summary
User: "요약해줘" → generate_daily_summary
User: "수정해줘" (after summary) → edit_daily_summary
User: "괜찮아" (after summary) → continue_daily_conversation
User: "나중에" → continue_daily_conversation

**CRITICAL**:
- NEVER respond without calling a tool
- Even simple greetings must use continue_daily_conversation
- Use conversation context to make accurate tool selections
"""

    return prompt


def determine_action_hint(
    user_context: UserContext,
    conv_state: Optional[Dict[str, Any]]
) -> Optional[str]:
    """action_hint 결정 (카카오톡 버튼용)"""

    if user_context.onboarding_stage != "completed":
        return "onboarding"

    if conv_state:
        current_step = conv_state.get("current_step", "")

        if current_step == "daily_summary_generated":
            return "daily_summary_edit"
        elif current_step == "weekly_feedback_generated":
            return "weekly_feedback"
        elif current_step.startswith("daily"):
            return "daily_record"

    return "daily_record"
