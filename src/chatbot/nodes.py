from .state import OverallState, UserContext, UserMetadata, OnboardingStage, OnboardingResponse, UserIntent
from ..utils.utils import get_system_prompt, format_user_prompt
from ..prompt.onboarding import ONBOARDING_SYSTEM_PROMPT, ONBOARDING_USER_PROMPT_TEMPLATE
from ..prompt.daily_record_prompt import DAILY_CONVERSATION_SYSTEM_PROMPT
from ..prompt.intent_classifier import SERVICE_ROUTER_SYSTEM_PROMPT, SERVICE_ROUTER_USER_PROMPT
from ..service import classify_user_intent, generate_daily_summary, generate_weekly_feedback
from langchain_openai import ChatOpenAI
from ..utils.models import CHAT_MODEL_CONFIG
import logging
from typing import Literal
from langgraph.types import Command
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from datetime import datetime
import os
from langsmith import traceable

logger = logging.getLogger(__name__)


# =============================================================================
# 1. Router Node - 온보딩 완료 체크
# =============================================================================

@traceable(name="router_node")
async def router_node(state: OverallState, db) -> Command[Literal["onboarding_agent_node", "service_router_node"]]:
    """온보딩 완료 여부 체크 후 분기"""
    user_id = state["user_id"]
    logger.info(f"🔀 [RouterNode] 시작 - user_id={user_id}")

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

        # conversation_states에서 세션 상태 복원
        conv_state = await db.get_conversation_state(user_id)
        daily_session_data = {}

        if conv_state and conv_state.get("temp_data"):
            temp_data = conv_state["temp_data"]
            metadata.field_attempts = temp_data.get("field_attempts", {})
            metadata.field_status = temp_data.get("field_status", {})
            daily_session_data = temp_data.get("daily_session_data", {})
            logger.debug(f"[RouterNode] Restored temp_data for user_id={user_id}")

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

        logger.info(f"[RouterNode] onboarding_complete={is_complete}, user_id={user_id}")

        user_context = UserContext(
            user_id=user_id,
            onboarding_stage=OnboardingStage.COMPLETED if is_complete else OnboardingStage.COLLECTING_BASIC,
            metadata=metadata,
            daily_record_count=user.get("daily_record_count", 0),
            last_record_date=user.get("last_record_date"),
            daily_session_data=daily_session_data
        )

        # 온보딩 완료 여부에 따라 라우팅
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

@traceable(name="service_router_node")
async def service_router_node(state: OverallState, llm, db, memory_manager) -> Command[Literal["daily_agent_node", "weekly_agent_node", "__end__"]]:
    """사용자 의도 파악: 일일 기록 vs 주간 피드백"""
    message = state["message"]
    user_context = state["user_context"]
    user_id = state["user_id"]

    logger.info(f"[ServiceRouter] message={message[:50]}")

    try:
        # 온보딩 키워드 감지 (온보딩 완료 유저가 재시작 시도)
        message_lower = message.strip().lower()
        onboarding_keywords = ["온보딩", "처음부터", "초기화", "정보 수정"]

        if any(keyword in message_lower for keyword in onboarding_keywords):
            logger.info(f"[ServiceRouter] 온보딩 재시작 요청 감지 (완료된 유저)")
            ai_response = f"안녕하세요, {user_context.metadata.name}님! 온보딩 정보 수정은 현재 지원하지 않아요. 대신 오늘 하신 업무에 대해 이야기 나눠볼까요?"

            # 대화 저장
            await memory_manager.add_messages(user_id, message, ai_response, db)

            return Command(update={"ai_response": ai_response}, goto="__end__")

        # LLM으로 의도 분류
        user_prompt = SERVICE_ROUTER_USER_PROMPT.format(message=message)

        response = await llm.ainvoke([
            SystemMessage(content=SERVICE_ROUTER_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt)
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

@traceable(name="onboarding_agent_node")
async def onboarding_agent_node(state: OverallState, db, memory_manager, llm) -> Command[Literal["__end__"]]:
    """온보딩 대화 + 정보 추출 + DB 저장"""
    user_id = state["user_id"]
    message = state["message"]
    user_context = state["user_context"]

    print(f"🎯 [OnboardingAgent] 시작 - user_id: {user_id}, message: {message[:50]}")

    try:
        # 온보딩 히스토리 과다 감지 시 초기화 (실패 패턴 누적 방지)
        total_messages = await db.count_messages(user_id)
        if total_messages > 10:  # 10개 넘으면 실패 패턴으로 판단
            logger.warning(f"[OnboardingAgent] 대화 히스토리 과다 감지 ({total_messages}개) - 초기화")
            await db.delete_conversations(user_id)
            logger.info(f"[OnboardingAgent] 대화 히스토리 초기화 완료")

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

        # 온보딩: 최근 3개 대화 포함 (이름 확인 플로우: User 답변 → Bot 확인 질문 → User 확인)
        recent_messages = await db.get_conversation_history(user_id, limit=3)

        system_prompt = get_system_prompt()
        user_prompt = format_user_prompt(
            message, current_state, "", recent_messages,
            target_field=target_field, current_attempt=current_attempt
        )

        logger.info(f"[OnboardingAgent] target={target_field}, attempt={current_attempt}, message={message[:50]}")

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
                    # ✅ 원본 current_metadata에서 현재 시도 횟수 가져오기 (updated_metadata는 복사본이라 0으로 초기화됨)
                    current_attempts = current_metadata.field_attempts.get(current_target_field, 0)
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

        # 이미 완료된 유저가 재진입한 경우 프롬프트가 처리하도록 넘김
        was_already_complete = user_context.onboarding_stage == OnboardingStage.COMPLETED

        # 온보딩 완료 시 특별 메시지 (이미 완료된 유저 제외 - 프롬프트가 재시작 요청 처리)
        if is_onboarding_complete and not was_already_complete:
            completion_message = f"""🎉 {updated_metadata.name}님, 온보딩이 완료되었어요!

지금까지 공유해주신 소중한 이야기를 바탕으로, 앞으로 {updated_metadata.name}님의 커리어 여정을 함께하겠습니다.

📝 일일 기록 시작하기

이제부터는 매일 업무를 기록하며 성장을 돌아볼 수 있어요. 아래처럼 자유롭게 말씀해주세요:

• "오늘은 ___를 했어요"
• "오늘 어려웠던 점: ___"
• "오늘 배운 점: ___"

제가 {updated_metadata.name}님의 이야기를 듣고, 더 깊이 생각해볼 수 있는 질문들을 드릴게요.

언제든 편하게 말씀해주세요!
대시보드 링크: 추가추가!!!!"""

            ai_response = completion_message
            logger.info(f"[OnboardingAgent] 온보딩 완료! user={user_id}")

        # 대화 저장
        await memory_manager.add_messages(user_id, message, ai_response, db)

        # 온보딩 완료 후 대화 히스토리 초기화 (일일기록 시작 시 온보딩 대화 제외)
        if is_onboarding_complete and not was_already_complete:
            await db.delete_conversations(user_id)
            # 완료 메시지만 다시 저장
            await memory_manager.add_messages(user_id, "", ai_response, db)
            logger.info(f"[OnboardingAgent] 온보딩 대화 히스토리 초기화 완료")

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
# 4. Daily Agent Node - 일일 기록 처리 (턴 카운팅 제거, 대화 횟수 기반)
# =============================================================================

@traceable(name="daily_agent_node")
async def daily_agent_node(state: OverallState, db, memory_manager) -> Command[Literal["__end__", "weekly_agent_node"]]:
    """일일 기록 대화 (대화 횟수 기반, 5회 이상 시 요약 제안)"""

    user_id = state["user_id"]
    message = state["message"]
    user_context = state["user_context"]

    logger.info(f"[DailyAgent] user_id={user_id}, message={message[:50]}")

    try:
        # 대화 히스토리 로드
        recent_turns = await db.get_conversation_history(user_id, limit=20)
        metadata = user_context.metadata
        llm = ChatOpenAI(**CHAT_MODEL_CONFIG, api_key=os.getenv("OPENAI_API_KEY"))

        # 현재 세션의 대화 횟수 계산 (user + bot 쌍 = 1회)
        current_session_count = user_context.daily_session_data.get("conversation_count", 0)
        logger.info(f"[DailyAgent] 현재 대화 횟수: {current_session_count}")

        # ========================================
        # 사용자 의도 분류: 요약 요청 vs 일반 대화
        # ========================================
        user_intent = await classify_user_intent(message, llm)

        # 요약 요청
        if "summary" in user_intent:
            logger.info(f"[DailyAgent] 요약 생성 요청")

            # 요약 생성
            ai_response, daily_count = await generate_daily_summary(
                user_id, metadata, {"recent_turns": recent_turns}, llm, db
            )

            # 7일차 체크 → weekly_agent_node로 라우팅
            if daily_count % 7 == 0:
                logger.info(f"[DailyAgent] 🎉 7일차 달성! → weekly_agent_node 라우팅")

                # 세션 초기화
                user_context.daily_session_data = {}

                # 대화 저장
                await memory_manager.add_messages(user_id, message, ai_response, db)

                # temp_data 업데이트
                existing_state = await db.get_conversation_state(user_id)
                existing_temp_data = existing_state.get("temp_data", {}) if existing_state else {}
                existing_temp_data["daily_session_data"] = {}
                existing_temp_data["daily_summary_response"] = ai_response  # 임시 저장
                existing_temp_data["daily_count"] = daily_count

                await db.upsert_conversation_state(
                    user_id,
                    current_step="daily_summary_completed",
                    temp_data=existing_temp_data
                )

                logger.info(f"[DailyAgent] 일일 요약 완료, weekly_agent_node로 라우팅")

                return Command(
                    update={"ai_response": ai_response, "user_context": user_context},
                    goto="weekly_agent_node"
                )

            # 7일차 아니면 종료
            user_context.daily_session_data = {}
            ai_response_final = ai_response

        # 재시작 요청
        elif "restart" in user_intent:
            logger.info(f"[DailyAgent] 재시작 요청")
            user_context.daily_session_data = {}
            ai_response_final = f"{metadata.name}님, 새로운 일일 기록을 시작하겠습니다! 오늘은 어떤 업무를 하셨나요?"

        # 일반 대화 (질문 생성)
        else:
            logger.info(f"[DailyAgent] 일반 대화 진행 ({current_session_count + 1}회차)")

            # 5회 이상 대화 시 요약 제안
            if current_session_count >= 5:
                logger.info(f"[DailyAgent] 5회 이상 대화 완료 → 요약 제안")
                ai_response_final = f"{metadata.name}님, 오늘도 많은 이야기 나눠주셨네요! 지금까지 내용을 정리해드릴까요?"
            else:
                # 자연스러운 질문 생성
                system_prompt = DAILY_CONVERSATION_SYSTEM_PROMPT.format(
                    name=metadata.name or "없음",
                    job_title=metadata.job_title or "없음",
                    total_years=metadata.total_years or "없음",
                    job_years=metadata.job_years or "없음",
                    career_goal=metadata.career_goal or "없음",
                    project_name=metadata.project_name or "없음",
                    recent_work=metadata.recent_work or "없음"
                )

                messages = [SystemMessage(content=system_prompt)]
                for turn in recent_turns[-10:]:
                    if turn["role"] == "user":
                        messages.append(HumanMessage(content=turn["content"]))
                    else:
                        messages.append(AIMessage(content=turn["content"]))
                messages.append(HumanMessage(content=message))

                response = await llm.ainvoke(messages)
                ai_response_final = response.content

                # 대화 횟수 증가
                user_context.daily_session_data["conversation_count"] = current_session_count + 1
                logger.info(f"[DailyAgent] ✅ 질문 생성 완료, 대화 횟수: {current_session_count} → {current_session_count + 1}")

        # ========================================
        # 공통: 대화 저장 + DB 업데이트
        # ========================================
        await memory_manager.add_messages(user_id, message, ai_response_final, db)

        existing_state = await db.get_conversation_state(user_id)
        existing_temp_data = existing_state.get("temp_data", {}) if existing_state else {}
        existing_temp_data["daily_session_data"] = user_context.daily_session_data or {}

        await db.upsert_conversation_state(
            user_id,
            current_step="daily_recording" if user_context.daily_session_data else "daily_summary_completed",
            temp_data=existing_temp_data
        )

        logger.info(f"[DailyAgent] 완료: conversation_count={current_session_count}")

        return Command(update={"ai_response": ai_response_final, "user_context": user_context}, goto="__end__")

    except Exception as e:
        logger.error(f"[DailyAgent] Error: {e}")
        import traceback
        traceback.print_exc()

        fallback_response = "처리 중 오류가 발생했습니다. 다시 시도해주세요."
        await memory_manager.add_messages(user_id, message, fallback_response, db)

        return Command(update={"ai_response": fallback_response}, goto="__end__")


# =============================================================================
# 5. Weekly Agent Node - 주간 피드백 생성 (7일차 자동 or 사용자 수동 요청)
# =============================================================================

@traceable(name="weekly_agent_node")
async def weekly_agent_node(state: OverallState, db, memory_manager) -> Command[Literal["__end__"]]:
    """주간 피드백 생성 및 DB 저장

    호출 경로:
    1. daily_agent_node → 7일차 달성 시 자동 라우팅
    2. service_router_node → 사용자가 수동으로 주간 피드백 요청
    """

    user_id = state["user_id"]
    message = state["message"]

    logger.info(f"[WeeklyAgent] user_id={user_id}, message={message}")

    try:
        # temp_data에서 일일 요약 응답 및 출석일 가져오기 (7일차 자동 트리거 시)
        conv_state = await db.get_conversation_state(user_id)
        temp_data = conv_state.get("temp_data", {}) if conv_state else {}
        daily_summary_response = temp_data.get("daily_summary_response")
        daily_count = temp_data.get("daily_count")

        # 주간 피드백 생성
        weekly_summary = await generate_weekly_feedback(user_id, db, memory_manager)

        # 7일차 자동 트리거인 경우: 일일 요약 + 주간 피드백 결합
        if daily_summary_response and daily_count and daily_count % 7 == 0:
            logger.info(f"[WeeklyAgent] 7일차 자동 트리거 (daily_count={daily_count})")

            ai_response = f"{daily_summary_response}\n\n{'='*50}\n🎉 **7일차 달성!**\n{'='*50}\n\n{weekly_summary}"

            # 주간요약 DB 저장
            sequence_number = daily_count // 7
            start_daily_count = (sequence_number - 1) * 7 + 1
            end_daily_count = sequence_number * 7
            current_date = datetime.now().date().isoformat()

            await db.save_weekly_summary(
                user_id=user_id,
                sequence_number=sequence_number,
                start_daily_count=start_daily_count,
                end_daily_count=end_daily_count,
                summary_content=weekly_summary,
                start_date=None,  # TODO: 일일기록 날짜 추적 추가 후 계산
                end_date=current_date
            )
            logger.info(f"[WeeklyAgent] ✅ 주간요약 DB 저장 완료: {sequence_number}번째 ({start_daily_count}-{end_daily_count}일차)")

            # temp_data 정리
            temp_data.pop("daily_summary_response", None)
            temp_data.pop("daily_count", None)
            await db.upsert_conversation_state(user_id, current_step="weekly_feedback_completed", temp_data=temp_data)

        # 수동 요청인 경우
        else:
            logger.info(f"[WeeklyAgent] 수동 요청")
            ai_response = weekly_summary

        # 대화 저장 (7일차는 daily_agent에서 이미 저장했으므로 수동 요청 시만 저장)
        if not daily_summary_response:
            await memory_manager.add_messages(user_id, message, ai_response, db)

        logger.info(f"[WeeklyAgent] 주간 피드백 생성 완료: {ai_response[:50]}...")

        return Command(update={"ai_response": ai_response}, goto="__end__")

    except Exception as e:
        logger.error(f"[WeeklyAgent] Error: {e}")
        import traceback
        traceback.print_exc()

        fallback_response = "주간 피드백 생성 중 오류가 발생했습니다."
        await memory_manager.add_messages(user_id, message, fallback_response, db)

        return Command(update={"ai_response": fallback_response}, goto="__end__")
