"""
LangGraph 워크플로우 노드들
"""

from .state import OverallState, UserContext, UserMetadata, OnboardingStage, OnboardingResponse, UserIntent
from ..utils.utils import get_system_prompt, format_user_prompt
import logging
from typing import Literal
from langgraph.types import Command
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from datetime import datetime

logger = logging.getLogger(__name__)


# =============================================================================
# 1. Router Node - 온보딩 완료 체크
# =============================================================================

async def router_node(state: OverallState, db) -> Command[Literal["onboarding_agent_node", "service_router_node"]]:
    """온보딩 완료 여부 체크 후 분기"""
    user_id = state["user_id"]

    try:
        # 사용자 정보 로드
        user = await db.get_user(user_id)

        if not user:
            # 신규 사용자
            user_context = UserContext(
                user_id=user_id,
                onboarding_stage=OnboardingStage.NOT_STARTED,
                metadata=UserMetadata()
            )
            return Command(update={"user_context": user_context}, goto="onboarding_agent_node")

        # 기존 사용자 - 메타데이터 구성
        # DB에는 field_attempts/field_status가 없으므로 제외
        DATA_FIELDS = ["name", "job_title", "total_years", "job_years", "career_goal",
                       "project_name", "recent_work", "job_meaning", "important_thing"]

        metadata = UserMetadata(**{
            k: user.get(k) for k in DATA_FIELDS
        })

        # 🆕 conversation_states에서 field_attempts/field_status 복원
        conv_state = await db.get_conversation_state(user_id)
        print(f"🔍 [RouterNode] conv_state: {conv_state}")

        if conv_state and conv_state.get("temp_data"):
            temp_data = conv_state["temp_data"]
            print(f"✅ [RouterNode] temp_data 복원: {temp_data}")

            if "field_attempts" in temp_data:
                metadata.field_attempts = temp_data["field_attempts"]
                print(f"✅ [RouterNode] field_attempts 복원: {metadata.field_attempts}")
            if "field_status" in temp_data:
                metadata.field_status = temp_data["field_status"]
                print(f"✅ [RouterNode] field_status 복원: {metadata.field_status}")
        else:
            print(f"⚠️ [RouterNode] temp_data 없음")

        # 온보딩 완료 체크 (9개 필드 전부 필수)
        is_complete = all([
            metadata.name,
            metadata.job_title,
            metadata.total_years,
            metadata.job_years,
            metadata.career_goal,
            metadata.project_name,
            metadata.recent_work,
            metadata.job_meaning,
            metadata.important_thing
        ])

        print(f"🔍 [RouterNode] 온보딩 완료 체크:")
        print(f"   - name: {metadata.name}")
        print(f"   - job_title: {metadata.job_title}")
        print(f"   - total_years: {metadata.total_years}")
        print(f"   - job_years: {metadata.job_years}")
        print(f"   - career_goal: {metadata.career_goal}")
        print(f"   - project_name: {metadata.project_name}")
        print(f"   - recent_work: {metadata.recent_work}")
        print(f"   - job_meaning: {metadata.job_meaning}")
        print(f"   - important_thing: {metadata.important_thing}")
        print(f"   - 온보딩 완료: {is_complete}")

        user_context = UserContext(
            user_id=user_id,
            onboarding_stage=OnboardingStage.COMPLETED if is_complete else OnboardingStage.COLLECTING_BASIC,
            metadata=metadata,
            daily_record_count=user.get("daily_record_count", 0),
            last_record_date=user.get("last_record_date")
        )

        if is_complete:
            return Command(update={"user_context": user_context}, goto="service_router_node")
        else:
            return Command(update={"user_context": user_context}, goto="onboarding_agent_node")

    except Exception as e:
        # 에러 시 기본 응답
        return Command(
            update={"ai_response": "죄송합니다. 오류가 발생했습니다."},
            goto="__end__"
        )


# =============================================================================
# 2. Service Router Node - 사용자 의도 파악
# =============================================================================

async def service_router_node(state: OverallState, llm) -> Command[Literal["daily_agent_node", "weekly_agent_node"]]:
    """사용자 의도 파악: 일일 기록 vs 주간 피드백"""
    message = state["message"]
    user_context = state["user_context"]

    logger.info(f"[ServiceRouter] message={message[:50]}")

    try:
        # LLM으로 의도 분류
        prompt = f"""사용자 메시지: "{message}"

위 메시지의 의도를 다음 중 하나로 분류해주세요:
- daily_record: 오늘 한 일, 업무 기록, 회고 등
- weekly_feedback: 주간 피드백, 이번 주 정리, 한 주 돌아보기 등

응답 형식: daily_record 또는 weekly_feedback"""

        response = await llm.ainvoke([
            SystemMessage(content="당신은 사용자 의도를 정확히 분류하는 전문가입니다."),
            HumanMessage(content=prompt)
        ])

        intent = response.content.strip().lower()

        if "weekly" in intent:
            logger.info(f"[ServiceRouter] Intent: weekly_feedback")
            return Command(update={"user_intent": UserIntent.WEEKLY_FEEDBACK.value}, goto="weekly_agent_node")
        else:
            logger.info(f"[ServiceRouter] Intent: daily_record")
            return Command(update={"user_intent": UserIntent.DAILY_RECORD.value}, goto="daily_agent_node")

    except Exception as e:
        logger.error(f"[ServiceRouter] Error: {e}, defaulting to daily_record")
        # 에러 시 기본값: 일일 기록
        return Command(update={"user_intent": UserIntent.DAILY_RECORD.value}, goto="daily_agent_node")


# =============================================================================
# 3. Onboarding Agent Node - 온보딩 처리
# =============================================================================

async def onboarding_agent_node(state: OverallState, db, memory_manager, llm) -> Command[Literal["__end__"]]:
    """온보딩 대화 + 정보 추출 + DB 저장"""
    user_id = state["user_id"]
    message = state["message"]
    user_context = state["user_context"]

    print(f"🎯 [OnboardingAgent] 시작 - user_id: {user_id}, message: {message[:50]}")

    try:
        # 대화 히스토리 로드
        conversation_context = await memory_manager.get_contextualized_history(user_id, db)

        # 현재 메시지를 히스토리에 임시 추가
        current_turn_history = conversation_context["recent_turns"] + [
            {"role": "user", "content": message}
        ]

        # 프롬프트 구성
        current_metadata = user_context.metadata if user_context.metadata else UserMetadata()
        current_state = current_metadata.dict()

        # 🆕 현재 타겟 필드와 시도 횟수 정보 추가
        FIELD_ORDER = ["name", "job_title", "total_years", "job_years", "career_goal",
                       "project_name", "recent_work", "job_meaning", "important_thing"]

        target_field = None
        for field in FIELD_ORDER:
            if not getattr(current_metadata, field):
                if current_metadata.field_status.get(field) != "skipped":
                    target_field = field
                    break

        current_attempt = current_metadata.field_attempts.get(target_field, 0) + 1 if target_field else 1

        system_prompt = get_system_prompt()
        user_prompt = format_user_prompt(
            message, current_state, conversation_context["summary"], current_turn_history,
            target_field=target_field, current_attempt=current_attempt
        )

        # 🔍 디버깅: LLM에게 전달되는 컨텍스트 확인
        print(f"\n{'='*80}")
        print(f"🔍 [OnboardingAgent] LLM에게 전달되는 정보:")
        print(f"📝 현재 타겟 필드: {target_field}")
        print(f"📝 시도 횟수: {current_attempt}")
        print(f"📝 유저 메시지: {message}")
        print(f"📝 대화 히스토리 (최근 5개):")
        if state.get("conversation_history"):
            for msg in state["conversation_history"][-5:]:
                role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "type", "unknown")
                content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
                print(f"   - {role}: {str(content)[:100]}...")
        print(f"{'='*80}\n")

        # LLM 호출 (structured output)
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ])

        # 정보 추출
        updated_metadata = user_context.metadata.copy() if user_context.metadata else UserMetadata()

        # 🆕 현재 타겟 필드 결정 (최우선 null 필드)
        FIELD_ORDER = ["name", "job_title", "total_years", "job_years", "career_goal",
                       "project_name", "recent_work", "job_meaning", "important_thing"]

        current_target_field = None
        for field in FIELD_ORDER:
            if not getattr(updated_metadata, field):
                # skipped 필드는 건너뛰기
                if updated_metadata.field_status.get(field) != "skipped":
                    current_target_field = field
                    break

        if isinstance(response, OnboardingResponse):
            # 필드 업데이트
            if response.name: updated_metadata.name = response.name
            if response.job_title: updated_metadata.job_title = response.job_title
            if response.total_years: updated_metadata.total_years = response.total_years
            if response.job_years: updated_metadata.job_years = response.job_years
            if response.career_goal: updated_metadata.career_goal = response.career_goal
            if response.project_name: updated_metadata.project_name = response.project_name
            if response.recent_work: updated_metadata.recent_work = response.recent_work
            if response.job_meaning: updated_metadata.job_meaning = response.job_meaning
            if response.important_thing: updated_metadata.important_thing = response.important_thing

            # 🆕 LLM이 판단한 field_status 병합
            if response.field_status:
                updated_metadata.field_status.update(response.field_status)

            # 🆕 현재 타겟 필드의 시도 횟수 증가 (명확화 요청이 아닐 때만)
            if current_target_field:
                if response.is_clarification_request:
                    print(f"💬 [OnboardingAgent] 명확화 요청 감지 - 시도 횟수 유지 (field: {current_target_field})")
                else:
                    current_attempts = updated_metadata.field_attempts.get(current_target_field, 0)
                    updated_metadata.field_attempts[current_target_field] = current_attempts + 1
                    print(f"📊 [OnboardingAgent] {current_target_field} 시도 횟수: {current_attempts} → {current_attempts + 1}")

                    # 3회 시도 후에도 null이면 스킵 (단, 유저의 마지막 답변은 보존)
                    if current_attempts + 1 >= 3 and not getattr(updated_metadata, current_target_field):
                        # 유저가 뭔가 말했다면 그것을 "INSUFFICIENT: {답변}" 형태로 저장
                        user_raw_answer = message.strip()
                        if user_raw_answer and user_raw_answer not in ["건너뛰기", "모름", "나중에", "skip"]:
                            setattr(updated_metadata, current_target_field, f"[INSUFFICIENT] {user_raw_answer}")
                            updated_metadata.field_status[current_target_field] = "insufficient"
                        else:
                            # 유저가 명시적으로 스킵 요청
                            updated_metadata.field_status[current_target_field] = "skipped"

            ai_response = response.response
        else:
            ai_response = str(response)

        # DB 업데이트 (null 값 및 내부 추적 필드 제외)
        db_data = {
            k: v for k, v in updated_metadata.dict().items()
            if v is not None and k not in ["field_attempts", "field_status"]
        }
        if db_data:  # 추출된 정보가 있을 때만 DB 업데이트
            await db.create_or_update_user(user_id, db_data)

        # 🆕 field_attempts와 field_status를 conversation_states.temp_data에 저장
        # 기존 temp_data 가져오기
        existing_state = await db.get_conversation_state(user_id)
        existing_temp_data = existing_state.get("temp_data", {}) if existing_state else {}

        # field_attempts와 field_status 병합
        existing_temp_data["field_attempts"] = updated_metadata.field_attempts
        existing_temp_data["field_status"] = updated_metadata.field_status

        print(f"💾 [OnboardingAgent] 저장할 field_attempts: {updated_metadata.field_attempts}")
        print(f"💾 [OnboardingAgent] 저장할 field_status: {updated_metadata.field_status}")
        print(f"💾 [OnboardingAgent] 저장할 temp_data: {existing_temp_data}")

        await db.upsert_conversation_state(
            user_id,
            current_step="onboarding",
            temp_data=existing_temp_data
        )

        print(f"✅ [OnboardingAgent] conversation_states 저장 완료")

        # 온보딩 완료 체크 (skipped/insufficient 모두 완료로 간주)
        REQUIRED_FIELDS = ["name", "job_title", "total_years", "job_years", "career_goal",
                          "project_name", "recent_work", "job_meaning", "important_thing"]

        filled_or_handled = []
        for field in REQUIRED_FIELDS:
            value = getattr(updated_metadata, field)
            status = updated_metadata.field_status.get(field)
            # 값이 있거나, skipped/insufficient 상태면 완료로 간주
            is_handled = value is not None or status in ["skipped", "insufficient"]
            filled_or_handled.append(is_handled)

        is_onboarding_complete = all(filled_or_handled)

        # 온보딩 완료 시 특별 메시지
        if is_onboarding_complete:
            completion_message = f"""🎉 {updated_metadata.name}님, 온보딩이 완료되었어요!

지금까지 공유해주신 소중한 이야기를 바탕으로, 앞으로 {updated_metadata.name}님의 커리어 여정을 함께하겠습니다.

📝 **일일 기록 시작하기**

이제부터는 매일 업무를 기록하며 성장을 돌아볼 수 있어요. 아래처럼 자유롭게 말씀해주세요:

• "오늘은 ___를 했어요"
• "오늘 어려웠던 점: ___"
• "오늘 배운 점: ___"

제가 {updated_metadata.name}님의 이야기를 듣고, 더 깊이 생각해볼 수 있는 질문들을 드릴게요.

언제든 편하게 말씀해주세요! 💬"""

            ai_response = completion_message
            logger.info(f"[OnboardingAgent] 온보딩 완료! user={user_id}")

        # 대화 저장
        await memory_manager.add_messages(user_id, message, ai_response, db)

        logger.info(f"[OnboardingAgent] 응답: {ai_response[:50]}...")

        return Command(update={"ai_response": ai_response}, goto="__end__")

    except Exception as e:
        logger.error(f"[OnboardingAgent] Error: {e}")
        import traceback
        traceback.print_exc()

        fallback_response = "죄송합니다. 오류가 발생했습니다."
        await memory_manager.add_messages(user_id, message, fallback_response, db)

        return Command(update={"ai_response": fallback_response}, goto="__end__")


# =============================================================================
# 4. Daily Agent Node - 일일 기록 처리
# =============================================================================

async def daily_agent_node(state: OverallState, db, memory_manager, agent_executor) -> Command[Literal["__end__"]]:
    """일일 기록 대화 + DB 저장"""
    from ..prompt.qa_agent import DAILY_AGENT_SYSTEM_PROMPT

    user_id = state["user_id"]
    message = state["message"]
    user_context = state["user_context"]

    logger.info(f"[DailyAgent] user_id={user_id}")

    try:
        # 대화 히스토리 로드
        conversation_context = await memory_manager.get_contextualized_history(user_id, db)

        # 오늘 날짜의 일일 기록 횟수 계산 (온보딩 제외)
        today = datetime.now().strftime("%Y-%m-%d")

        # conversations 테이블에서 오늘 날짜의 user 메시지만 카운트
        # (온보딩 완료 후의 메시지만 카운트하려면 onboarding_stage가 COMPLETED인 시점 이후)
        today_count = 0
        for turn in conversation_context["recent_turns"]:
            if turn["role"] == "user" and turn.get("created_at", "").startswith(today):
                today_count += 1

        # 시스템 프롬프트 구성
        metadata = user_context.metadata
        system_prompt = DAILY_AGENT_SYSTEM_PROMPT.format(
            name=metadata.name or "없음",
            job_title=metadata.job_title or "없음",
            total_years=metadata.total_years or "없음",
            job_years=metadata.job_years or "없음",
            career_goal=metadata.career_goal or "없음",
            project_name=metadata.project_name or "없음",
            recent_work=metadata.recent_work or "없음",
            today_record_count=today_count
        )

        # 메시지 구성
        messages = [SystemMessage(content=system_prompt)]

        for turn in conversation_context["recent_turns"][-5:]:
            if turn["role"] == "user":
                messages.append(HumanMessage(content=turn["content"]))
            else:
                messages.append(AIMessage(content=turn["content"]))

        messages.append(HumanMessage(content=message))

        # AgentExecutor 실행
        result = await agent_executor.ainvoke({"messages": messages})
        ai_response = result["messages"][-1].content

        # 대화 저장
        await memory_manager.add_messages(user_id, message, ai_response, db)

        logger.info(f"[DailyAgent] 응답: {ai_response[:50]}..., today_count={today_count}")

        return Command(update={"ai_response": ai_response}, goto="__end__")

    except Exception as e:
        logger.error(f"[DailyAgent] Error: {e}")
        import traceback
        traceback.print_exc()

        fallback_response = "처리 중 오류가 발생했습니다. 다시 시도해주세요."
        await memory_manager.add_messages(user_id, message, fallback_response, db)

        return Command(update={"ai_response": fallback_response}, goto="__end__")


# =============================================================================
# 5. Weekly Agent Node - 주간 피드백 생성
# =============================================================================

async def weekly_agent_node(state: OverallState, db, memory_manager, agent_executor) -> Command[Literal["__end__"]]:
    """주간 피드백 생성"""
    from ..prompt.qa_agent import UNIFIED_AGENT_SYSTEM_PROMPT

    user_id = state["user_id"]
    message = state["message"]
    user_context = state["user_context"]

    logger.info(f"[WeeklyAgent] user_id={user_id}")

    try:
        # TODO: DB에서 주간 데이터 조회 (최근 7일간의 conversations)
        # 현재는 임시로 대화 히스토리 사용
        conversation_context = await memory_manager.get_contextualized_history(user_id, db)

        # 시스템 프롬프트 구성
        metadata = user_context.metadata
        system_prompt = f"""당신은 주간 피드백을 제공하는 커리어 코치입니다.

사용자 정보:
- 이름: {metadata.name}
- 직무: {metadata.job_title}
- 목표: {metadata.career_goal}

최근 대화 요약:
{conversation_context["summary"]}

사용자의 주간 활동을 분석하여 다음을 포함한 피드백을 한국어로 제공하세요:
1. 이번 주 하이라이트 (주요 성과 3가지)
2. 발견된 패턴 (업무 패턴, 성장 포인트)
3. 다음 주 제안 (개선 방향, 실행 가능한 조언)

격려하고 긍정적인 톤으로 작성해주세요."""

        # 메시지 구성
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=message)
        ]

        # AgentExecutor 실행
        result = await agent_executor.ainvoke({"messages": messages})
        ai_response = result["messages"][-1].content

        # 대화 저장
        await memory_manager.add_messages(user_id, message, ai_response, db)

        logger.info(f"[WeeklyAgent] 응답: {ai_response[:50]}...")

        return Command(update={"ai_response": ai_response}, goto="__end__")

    except Exception as e:
        logger.error(f"[WeeklyAgent] Error: {e}")
        import traceback
        traceback.print_exc()

        fallback_response = "주간 피드백 생성 중 오류가 발생했습니다."
        await memory_manager.add_messages(user_id, message, fallback_response, db)

        return Command(update={"ai_response": fallback_response}, goto="__end__")
