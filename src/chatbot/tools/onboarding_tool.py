"""온보딩 툴 - 사용자 정보 수집"""
from typing import Any, Optional, Dict
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
from ..state import UserMetadata
from ...database.user_repository import (
    save_onboarding_metadata,
    complete_onboarding,
    get_user_with_context
)
from ...prompt.onboarding_extraction import EXTRACTION_SYSTEM_PROMPT, EXTRACTION_USER_PROMPT_TEMPLATE, FIELD_DESCRIPTIONS
from ...helpers.onboarding_questions import (
    get_field_template, get_next_field,
    format_welcome_message, format_completion_message,
    get_progress_indicator,
    FIELD_ORDER
)
from langchain_core.messages import SystemMessage, HumanMessage
import logging

logger = logging.getLogger(__name__)


class OnboardingTool(BaseTool):
    """온보딩 대화 처리 툴"""
    name: str = "handle_onboarding"
    description: str = """사용자의 온보딩을 처리합니다.
    이름, 직무, 연차, 목표 등 9개 필드를 순차적으로 수집합니다.

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
        """온보딩 처리 - nodes.py의 onboarding_agent_node 로직 그대로 사용"""
        from ..state import ExtractionResponse, OnboardingIntent
        from ...helpers.models import get_onboarding_llm

        logger.info(f"[OnboardingTool] ✅ 도구 호출됨 - user_id={user_id}, message={message[:50]}")

        # ========================================
        # 1. 현재 상태 로드
        # ========================================
        _, user_context = await get_user_with_context(self.db, user_id)
        current_metadata = user_context.metadata if user_context.metadata else UserMetadata()

        # 첫 온보딩인 경우 환영 메시지 (conversation_states로 체크)
        conv_state = await self.db.get_conversation_state(user_id)
        has_onboarding_messages = False
        if conv_state and conv_state.get("temp_data"):
            has_onboarding_messages = "onboarding_messages" in conv_state["temp_data"]

        is_first_onboarding = not has_onboarding_messages and all(getattr(current_metadata, field) is None for field in FIELD_ORDER)

        if is_first_onboarding:
            welcome_msg = format_welcome_message()
            first_template = get_field_template("name")
            first_question = first_template.get_question(1)
            ai_response = f"{welcome_msg}\n\n{first_question}"

            # 메타데이터 초기화 (field_attempts, field_status 저장)
            await save_onboarding_metadata(self.db, user_id, current_metadata)

            # 대화 히스토리 저장
            conv_state_updated = await self.db.get_conversation_state(user_id)
            existing_temp_data = conv_state_updated.get("temp_data", {}) if conv_state_updated else {}
            existing_temp_data["onboarding_messages"] = [{"role": "assistant", "content": ai_response}]

            await self.db.upsert_conversation_state(
                user_id,
                current_step="onboarding",
                temp_data=existing_temp_data
            )

            return ai_response

        # ========================================
        # 2. 다음 수집할 필드 결정
        # ========================================
        target_field = get_next_field(current_metadata.dict())

        if not target_field:
            # 모든 필드 완료
            await complete_onboarding(self.db, user_id)
            completion_msg = format_completion_message(current_metadata.name)
            logger.info(f"[OnboardingTool] ✅ 온보딩 완료! user={user_id}")
            return completion_msg

        # ========================================
        # 3. 대화 히스토리 로드 + LLM으로 정보 추출
        # ========================================
        conv_state = await self.db.get_conversation_state(user_id)
        recent_messages = []
        if conv_state and conv_state.get("temp_data"):
            recent_messages = conv_state["temp_data"].get("onboarding_messages", [])[-6:]

        # 대화 히스토리 포맷팅
        history_text = ""
        if recent_messages:
            for msg in recent_messages[-2:]:  # 최근 1턴만
                role = "봇" if msg["role"] == "assistant" else "사용자"
                history_text += f"{role}: {msg['content']}\n"

        field_description = FIELD_DESCRIPTIONS.get(target_field, "")
        extraction_prompt = EXTRACTION_USER_PROMPT_TEMPLATE.format(
            target_field=target_field,
            field_description=field_description,
            user_message=message[:300]
        )

        full_prompt = f"""**대화 컨텍스트:**
{history_text if history_text else "(첫 메시지)"}

{extraction_prompt}"""

        # LLM 호출
        base_llm = get_onboarding_llm()
        extraction_llm = base_llm.with_structured_output(ExtractionResponse)

        extraction_result = await extraction_llm.ainvoke([
            SystemMessage(content=EXTRACTION_SYSTEM_PROMPT),
            HumanMessage(content=full_prompt)
        ])

        if extraction_result is None:
            ai_response = "죄송합니다. 잠시 문제가 발생했어요. 다시 한 번 말씀해주시겠어요?"
            # 에러 시에도 히스토리 저장
            await self._save_conversation_history(user_id, message, ai_response, conv_state)
            return ai_response

        logger.info(f"🤖 [LLM 추출 결과] intent={extraction_result.intent}, value={extraction_result.extracted_value}, confidence={extraction_result.confidence}")

        # ========================================
        # 4. 추출 결과에 따른 처리 (nodes.py 로직 그대로)
        # ========================================
        updated_metadata = current_metadata.copy()
        current_attempt = updated_metadata.field_attempts.get(target_field, 0)
        field_template = get_field_template(target_field)
        user_name = updated_metadata.name

        if extraction_result.intent == OnboardingIntent.CLARIFICATION:
            # 명확화 요청 - 시도 횟수 증가하고 더 자세한 질문 제공
            updated_metadata.field_attempts[target_field] = current_attempt + 1
            new_attempt = updated_metadata.field_attempts[target_field]
            next_question = field_template.get_question(min(new_attempt + 1, 3), name=user_name)

            progress = get_progress_indicator(updated_metadata.dict())
            ai_response = f"{progress}\n\n{next_question}"

        elif extraction_result.intent == OnboardingIntent.INVALID:
            # 무관한 응답 - 시도 횟수 증가 후 재질문 또는 스킵
            updated_metadata.field_attempts[target_field] = current_attempt + 1
            new_attempt = updated_metadata.field_attempts[target_field]

            # 3회 이상 시도 시 스킵 처리
            if new_attempt >= 3:
                updated_metadata.field_status[target_field] = "insufficient"
                setattr(updated_metadata, target_field, f"[SKIPPED] 응답 거부")
                logger.info(f"⚠️ [{target_field}] 3회 무관한 응답 - 스킵 처리")

                # 다음 필드로 이동
                next_field = get_next_field(updated_metadata.dict())

                if next_field:
                    next_template = get_field_template(next_field)
                    next_question = next_template.get_question(1, name=updated_metadata.name)
                    progress = get_progress_indicator(updated_metadata.dict())
                    ai_response = f"{progress}\n\n{next_question}"
                else:
                    # 온보딩 완료
                    await complete_onboarding(self.db, user_id)
                    ai_response = format_completion_message(updated_metadata.name)

                await save_onboarding_metadata(self.db, user_id, updated_metadata)
                await self._save_conversation_history(user_id, message, ai_response, conv_state)
                return ai_response
            else:
                # 재질문
                logger.info(f"⚠️ [{target_field}] 무관한 응답 ({new_attempt}/3회) - 재질문")
                next_question = field_template.get_question(min(new_attempt + 1, 3), name=user_name)
                progress = get_progress_indicator(updated_metadata.dict())
                ai_response = f"{progress}\n\n{next_question}"

                await save_onboarding_metadata(self.db, user_id, updated_metadata)
                await self._save_conversation_history(user_id, message, ai_response, conv_state)
                return ai_response

        elif extraction_result.intent == OnboardingIntent.ANSWER:
            # 답변 제공됨
            extracted_value = extraction_result.extracted_value
            confidence = extraction_result.confidence

            # 신뢰도 체크: 0.5 미만이면 명확화 필요
            if confidence < 0.5:
                updated_metadata.field_attempts[target_field] = current_attempt + 1
                new_attempt = updated_metadata.field_attempts[target_field]
                logger.info(f"⚠️ [{target_field}] 신뢰도 낮음 (conf={confidence:.2f}) - 명확화 요청")
                ai_response = field_template.get_question(min(new_attempt + 1, 3), name=user_name)
                await save_onboarding_metadata(self.db, user_id, updated_metadata)
                await self._save_conversation_history(user_id, message, ai_response, conv_state)
                return ai_response

            # 신입 특수 처리
            if target_field == "total_years" and extracted_value and "신입" in extracted_value:
                updated_metadata.total_years = "신입"
                updated_metadata.job_years = "신입"
                updated_metadata.field_status["total_years"] = "filled"
                updated_metadata.field_status["job_years"] = "filled"
                updated_metadata.field_attempts["total_years"] = current_attempt + 1
                updated_metadata.field_attempts["job_years"] = 0
                logger.info(f"✅ [신입 감지] total_years, job_years 모두 '신입'으로 설정")

                # career_goal로 이동
                next_field = "career_goal"
            else:
                # 검증
                if field_template.validate(extracted_value):
                    setattr(updated_metadata, target_field, extracted_value)
                    updated_metadata.field_status[target_field] = "filled"
                    updated_metadata.field_attempts[target_field] = current_attempt + 1
                    logger.info(f"✅ [{target_field}] 값 저장: {extracted_value}")

                    # 다음 필드
                    next_field = get_next_field(updated_metadata.dict())
                else:
                    # 검증 실패
                    updated_metadata.field_attempts[target_field] = current_attempt + 1
                    logger.info(f"❌ [{target_field}] 검증 실패: {extracted_value}")
                    next_field = target_field  # 같은 필드 재시도

            # 시도 횟수 체크 (3회 초과 시 스킵)
            if updated_metadata.field_attempts.get(target_field, 0) >= 3:
                updated_metadata.field_status[target_field] = "insufficient"
                setattr(updated_metadata, target_field, f"[INSUFFICIENT] {extracted_value or message[:50]}")
                next_field = get_next_field(updated_metadata.dict())

            # 다음 질문 생성
            if next_field == target_field:
                # 같은 필드 재시도 (검증 실패 케이스)
                next_attempt_count = updated_metadata.field_attempts.get(next_field, 0)
                next_question = field_template.get_question(min(next_attempt_count + 1, 3), name=user_name)
                progress = get_progress_indicator(updated_metadata.dict())
                ai_response = f"{progress}\n\n{next_question}"
            elif next_field:
                # 다른 필드로 이동 (성공 케이스)
                next_template = get_field_template(next_field)
                next_question = next_template.get_question(1, name=updated_metadata.name)
                progress = get_progress_indicator(updated_metadata.dict())
                ai_response = f"{progress}\n\n{next_question}"
            else:
                # 완료
                logger.info(f"💾 [OnboardingTool] 온보딩 완료 - 메타데이터 저장")
                await save_onboarding_metadata(self.db, user_id, updated_metadata)
                await complete_onboarding(self.db, user_id)
                ai_response = format_completion_message(updated_metadata.name)
                logger.info(f"✅ [OnboardingTool] 🎉 온보딩 완료")
                return ai_response

        else:  # INVALID
            # 무관한 내용 - 현재 필드 재질문
            updated_metadata.field_attempts[target_field] = current_attempt + 1
            new_attempt = updated_metadata.field_attempts[target_field]
            ai_response = field_template.get_question(min(new_attempt + 1, 3), name=user_name)

        # ========================================
        # 5. 메타데이터 저장 + 대화 히스토리 저장 (항상!)
        # ========================================
        await save_onboarding_metadata(self.db, user_id, updated_metadata)
        await self._save_conversation_history(user_id, message, ai_response, conv_state)

        return ai_response

    async def _save_conversation_history(self, user_id: str, message: str, ai_response: str, conv_state: Optional[Dict[str, Any]]):
        """대화 히스토리 저장 헬퍼 (nodes.py 로직 그대로)"""
        existing_temp_data = conv_state.get("temp_data", {}) if conv_state else {}
        recent_messages = existing_temp_data.get("onboarding_messages", [])[-6:]

        recent_messages.append({"role": "user", "content": message})
        recent_messages.append({"role": "assistant", "content": ai_response})
        recent_messages = recent_messages[-6:]  # 최근 3턴만 유지

        existing_temp_data["onboarding_messages"] = recent_messages
        await self.db.upsert_conversation_state(
            user_id,
            current_step="onboarding",
            temp_data=existing_temp_data
        )
