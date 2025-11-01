"""일일 대화 툴 - 업무 관련 대화 (nodes.py:537-876 전체 로직)"""
from typing import Any
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
from ...database.user_repository import (
    check_and_reset_daily_count,
    get_user_with_context,
    increment_counts_with_check
)
from ...core.intent_classifier import classify_user_intent
from ...prompt.daily_record import DAILY_CONVERSATION_SYSTEM_PROMPT
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class DailyConversationTool(BaseTool):
    """일일 업무 대화 툴 - nodes.py:537-876 로직 완전 마이그레이션"""
    name: str = "continue_daily_conversation"
    description: str = """사용자와 일일 업무에 대해 대화를 이어갑니다.
    업무 내용을 듣고 후속 질문을 합니다.

    입력: user_id (문자열), message (문자열)
    출력: AI 응답 메시지"""
    return_direct: bool = True  # 🚨 툴의 반환값을 바로 최종 응답으로 사용

    db: Any = Field(exclude=True)
    llm: Any = Field(exclude=True)

    class Config:
        arbitrary_types_allowed = True

    # LLM이 생성할 파라미터 스키마 정의
    class InputSchema(BaseModel):
        user_id: str = Field(description="카카오 사용자 ID")
        message: str = Field(description="사용자 메시지")

    args_schema = InputSchema

    def _run(self, user_id: str, message: str) -> str:
        raise NotImplementedError("Use async version")

    async def _arun(self, user_id: str, message: str) -> str:
        """일일 대화 처리 - nodes.py:537-876 전체 로직

        특수 의도별 하드코딩 응답 + 일반 대화 처리 + is_valid_turn 기반 카운트 제어
        """
        logger.info(f"[DailyConversationTool] ✅ 도구 호출됨 - user_id={user_id}, message={message[:50]}")

        # ========================================
        # 1. 초기 데이터 로드 (기존 nodes.py:552-577)
        # ========================================
        _, user_context = await get_user_with_context(self.db, user_id)

        # 🚨 온보딩 완료 당일 재시작 시도 차단 (첫 기록 전) - 최우선 체크
        # last_record_date가 None이면 → 온보딩 완료 후 아직 한 번도 기록 안 한 상태
        if user_context.last_record_date is None and user_context.onboarding_stage.value == "completed":
            logger.info(f"[DailyConversationTool] 온보딩 완료 당일 재시작 시도 감지 → 안내 멘트")

            metadata = user_context.metadata
            ai_response_final = f"{metadata.name}님, 내일부터 업무기록을 시작할 수 있어요. 잊지 않도록 <3분커리어>가 알림할게요!"

            # 대화 저장 (카운트 증가 X)
            await self.db.save_conversation_turn(
                user_id,
                message,
                ai_response_final,
                is_summary=False
            )

            logger.info(f"[DailyConversationTool] 온보딩 당일 재시작 차단 완료")
            return ai_response_final

        conv_state = await self.db.get_conversation_state(user_id)
        recent_turns = await self.db.get_recent_turns_v2(user_id, limit=10)

        # 날짜 변경 체크 및 리셋
        current_attendance, was_reset = await check_and_reset_daily_count(self.db, user_id)

        # conversation_states.temp_data.daily_session_data에서 가져오기
        daily_session_data = {}
        if conv_state and conv_state.get("temp_data"):
            daily_session_data = conv_state["temp_data"].get("daily_session_data", {})

        conversation_count = daily_session_data.get("conversation_count", 0)
        if was_reset:
            conversation_count = 0

        logger.info(f"[DailyConversationTool] 현재 대화 횟수: {conversation_count}")

        metadata = user_context.metadata
        is_valid_turn = True  # 🚨 유효한 대화 턴인지 (카운트 증가 여부)

        # ========================================
        # 2. 사용자 의도 분류 (기존 nodes.py:591-601)
        # ========================================
        # 직전 봇 메시지 추출
        last_bot_message = None
        if recent_turns:
            last_turn = recent_turns[-1] if recent_turns else None
            if last_turn and last_turn.get("ai_message"):
                last_bot_message = last_turn["ai_message"]

        # enhanced_message 생성
        enhanced_message = f"[Previous bot]: {last_bot_message}\n[User]: {message}" if last_bot_message else message

        # 의도 분류
        user_intent = await classify_user_intent(enhanced_message, self.llm, user_context, self.db)
        logger.info(f"[DailyConversationTool] 의도 분류: {user_intent}")

        # ========================================
        # 3. 의도별 처리 (기존 nodes.py:602-814)
        # ========================================

        # 온보딩 완료 후 시작 선택 (기존 nodes.py:602-609)
        if "onboarding_start_accepted" in user_intent:
            logger.info(f"[DailyConversationTool] 온보딩 완료 후 시작 선택 → 첫 질문 생성 (카운트 증가 X)")
            ai_response_final = f"좋아요, {metadata.name}님! 그럼 오늘 하신 업무에 대해 이야기 나눠볼까요?"
            is_valid_turn = False

            # 세션 초기화
            daily_session_data = {}

        # 오늘 기록 없이 요약 요청한 경우 (기존 nodes.py:610-616)
        elif "no_record_today" in user_intent:
            logger.info(f"[DailyConversationTool] 오늘 날짜 기록 없이 요약 요청 → 거부 (카운트 증가 X)")
            ai_response_final = f"{metadata.name}님, 오늘의 일일기록을 먼저 진행해주세요! 오늘 하신 업무에 대해 이야기 나눠볼까요?"
            is_valid_turn = False

            # 세션 초기화
            daily_session_data = {}

        # 거절 (기존 nodes.py:617-622)
        elif "rejection" in user_intent:
            logger.info(f"[DailyConversationTool] 거절 감지 → 세션 초기화 (카운트 증가 X)")
            ai_response_final = f"알겠습니다, {metadata.name}님! 다시 시작할 때 편하게 말씀해주세요."
            is_valid_turn = False

            # 세션 초기화
            daily_session_data = {}

        # 대화 종료 요청 (기존 nodes.py:624-637)
        elif "end_conversation" in user_intent:
            logger.info(f"[DailyConversationTool] 대화 종료 요청")

            # 🚨 3턴 미만이면 출석 경고
            current_daily_count = user_context.daily_record_count
            if current_daily_count < 3:
                remaining = 3 - current_daily_count
                ai_response_final = f"{metadata.name}님, 오늘 출석 체크가 아직 완료되지 않았어요! (현재 {current_daily_count}/3턴)\n{remaining}턴만 더 대화하시면 출석이 인정됩니다.\n\n그래도 종료하시겠어요?"
            else:
                ai_response_final = f"좋아요 {metadata.name}님, 오늘도 수고하셨습니다! 내일 다시 만나요 😊"

            is_valid_turn = False

            # 세션 종료
            daily_session_data = {}

        # 수정 불필요 (기존 nodes.py:639-646)
        # 🚨 중요: 요약이 방금 생성된 경우에만 종료 처리
        elif "no_edit_needed" in user_intent and daily_session_data.get("last_summary_at"):
            logger.info(f"[DailyConversationTool] 수정 불필요 (요약 후) → 깔끔하게 마무리 (카운트 증가 X)")
            ai_response_final = f"좋아요 {metadata.name}님, 오늘도 수고하셨습니다! 내일 다시 만나요 😊"
            is_valid_turn = False

            # 세션 종료
            daily_session_data = {}

        # 재시작 요청 (기존 nodes.py:765-770)
        elif "restart" in user_intent:
            logger.info(f"[DailyConversationTool] 재시작 요청 → 세션 초기화 (카운트 증가 X)")
            ai_response_final = f"{metadata.name}님, 새로운 일일 기록을 시작하겠습니다! 오늘은 어떤 업무를 하셨나요?"
            is_valid_turn = False

            # 세션 초기화
            daily_session_data = {}

        # 일반 대화 (기존 nodes.py:772-818)
        else:
            logger.info(f"[DailyConversationTool] 일반 대화 진행 ({conversation_count + 1}회차)")

            # 🚨 Fallback: 요약 관련 키워드가 있지만 continue로 분류된 경우 (기존 nodes.py:776-784)
            summary_keywords = ["정리", "요약", "써머리", "summary"]
            message_lower = message.lower().replace(" ", "")
            has_summary_keyword = any(keyword in message_lower for keyword in summary_keywords)

            # 3회 이상 대화 완료 후 요약 제안했는데, 애매한 응답이 온 경우
            if conversation_count >= 3 and has_summary_keyword and len(message) < 20:
                logger.info(f"[DailyConversationTool] 애매한 요약 관련 입력 감지 → 명확화 요청")
                ai_response_final = f"{metadata.name}님, 좀 더 명확히 말씀해주시겠어요? 예를 들어 '오늘 업무 요약해줘' 또는 '나중에 할게'처럼 말씀해주세요."

            # 3회 이상 대화 시 요약 제안 (기존 nodes.py:787-789)
            # 🚨 중요: 하드코딩된 메시지, conversation_count 증가 안 함
            elif conversation_count >= 3:
                logger.info(f"[DailyConversationTool] 3회 이상 대화 완료 → 요약 제안 (카운트 증가 X)")
                ai_response_final = f"{metadata.name}님, 오늘도 많은 이야기 나눠주셨네요! 지금까지 내용을 정리해드릴까요?"
                # conversation_count는 증가하지 않음 (요약 수락 시 리셋될 것)

            # 3회 미만: LLM 생성 (기존 nodes.py:790-818)
            else:
                # 최근 3턴만 조회 (성능 최적화)
                recent_turns_for_context = await self.db.get_recent_turns_v2(user_id, limit=3)
                logger.info(f"[DailyConversationTool] 최근 대화 조회: {len(recent_turns_for_context)}턴")

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
                # 최근 3턴 사용 (메모리 최적화)
                for turn in recent_turns_for_context:
                    messages.append(HumanMessage(content=turn["user_message"]))
                    messages.append(AIMessage(content=turn["ai_message"]))
                messages.append(HumanMessage(content=message))

                response = await self.llm.ainvoke(messages)
                ai_response_final = response.content

                # 대화 횟수 증가 (기존 nodes.py:817-818)
                conversation_count += 1
                daily_session_data["conversation_count"] = conversation_count
                logger.info(f"[DailyConversationTool] ✅ 질문 생성 완료, 대화 횟수: {conversation_count}")

        # ========================================
        # 4. 공통: 대화 저장 + 카운트 증가 (기존 nodes.py:823-860)
        # ========================================
        await self.db.save_conversation_turn(
            user_id,
            message,
            ai_response_final,
            is_summary=False
        )

        # 🚨 중요: 카운트 증가 조건 (기존 nodes.py:829-853)
        should_increment = is_valid_turn

        if not is_valid_turn:
            logger.info(f"[DailyConversationTool] 유효하지 않은 턴 (거절/종료/특수케이스) - daily_record_count 증가 안 함")

        if should_increment:
            # Repository 함수로 카운트 증가 (daily_record_count + attendance_count 자동 처리)
            updated_daily_count, new_attendance = await increment_counts_with_check(self.db, user_id)

            if new_attendance:
                logger.info(f"[DailyConversationTool] 🎉 3회 달성! attendance_count 증가: {new_attendance}일차")

            logger.info(f"[DailyConversationTool] daily_record_count 업데이트: {updated_daily_count}회")

        # 세션 데이터 업데이트 (기존 nodes.py:854-860)
        existing_temp_data = conv_state.get("temp_data", {}) if conv_state else {}
        existing_temp_data["daily_session_data"] = daily_session_data

        current_step = "daily_conversation" if daily_session_data else "conversation_ended"

        await self.db.upsert_conversation_state(
            user_id,
            current_step=current_step,
            temp_data=existing_temp_data
        )

        logger.info(f"[DailyConversationTool] 대화 완료 - conversation_count={conversation_count}")

        return ai_response_final
