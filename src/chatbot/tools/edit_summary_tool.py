"""요약 수정 툴 - 생성된 요약 수정 (기존 nodes.py:648-677 로직)"""
from typing import Any
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
from ...database.user_repository import get_user_with_context, increment_counts_with_check
from ...database.summary_repository import prepare_daily_summary_data
from ...database.conversation_repository import set_weekly_summary_flag
from ...core.summary_generator import generate_daily_summary
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class EditSummaryTool(BaseTool):
    """요약 수정 툴 - user_correction을 시스템 프롬프트에 주입하여 정확한 수정"""
    name: str = "edit_daily_summary"
    description: str = """생성된 일일 요약을 사용자 요청에 따라 수정합니다.
    전체 대화 내용을 기반으로 user_correction을 시스템 프롬프트에 주입하여 재생성합니다.

    입력: user_id (문자열), message (문자열 - 사용자의 수정 요청)
    출력: 수정된 요약 텍스트"""
    return_direct: bool = True  # 🚨 툴의 반환값을 바로 최종 응답으로 사용

    db: Any = Field(exclude=True)
    llm: Any = Field(exclude=True)

    class Config:
        arbitrary_types_allowed = True

    # LLM이 생성할 파라미터 스키마 정의
    class InputSchema(BaseModel):
        user_id: str = Field(description="카카오 사용자 ID")
        message: str = Field(description="사용자의 수정 요청 메시지")

    args_schema = InputSchema

    def _run(self, user_id: str, message: str) -> str:
        raise NotImplementedError("Use async version")

    async def _arun(self, user_id: str, message: str) -> str:
        """요약 수정 - 기존 nodes.py:648-677 로직 그대로

        사용자 수정 요청을 시스템 프롬프트에 명시적으로 주입하여
        실제 대화 내용 기반으로 정확하게 재생성합니다.
        """
        logger.info(f"[EditSummaryTool] ✅ 도구 호출됨 - user_id={user_id}, message={message[:50]}")
        logger.info(f"[EditSummaryTool] 요약 수정 요청 → 사용자 피드백을 시스템 프롬프트에 명시적으로 주입")

        # 데이터 조회
        _, user_context = await get_user_with_context(self.db, user_id)

        # 요약 수정 시에도 오늘 전체 대화 조회 (기존 nodes.py:652-655)
        today = datetime.now().date().isoformat()
        all_today_turns = await self.db.get_conversation_history_by_date_v2(user_id, today, limit=50)
        logger.info(f"[EditSummaryTool] 요약 수정용 전체 대화 조회: {len(all_today_turns)}턴")

        # 요약 재생성 (기존 nodes.py:657-667)
        # user_correction을 통해 시스템 프롬프트에 명시적으로 주입됨
        input_data = await prepare_daily_summary_data(
            self.db,
            user_id,
            all_today_turns,
            user_correction=message  # 🎯 사용자의 수정 요청을 명시적으로 전달
        )
        output = await generate_daily_summary(input_data, self.llm)
        ai_response = output.summary_text
        current_attendance_count = input_data.attendance_count

        # 요약 플래그 설정
        is_summary_response = True
        summary_type_value = 'daily'

        # last_summary_at 업데이트 + conversation_count 리셋 (기존 nodes.py:674-677)
        conv_state = await self.db.get_conversation_state(user_id)
        existing_temp_data = conv_state.get("temp_data", {}) if conv_state else {}
        daily_session_data = existing_temp_data.get("daily_session_data", {})
        daily_session_data["last_summary_at"] = datetime.now().isoformat()
        daily_session_data["conversation_count"] = 0  # 리셋!
        existing_temp_data["daily_session_data"] = daily_session_data

        await self.db.upsert_conversation_state(
            user_id,
            current_step="daily_summary_generated",
            temp_data=existing_temp_data
        )
        logger.info(f"[EditSummaryTool] 요약 수정 완료 → conversation_count 리셋")

        # 🚨 중요: 요약 수정은 카운트에 포함 (기존 nodes.py:672, 841-843)
        updated_daily_count, new_attendance = await increment_counts_with_check(self.db, user_id)
        if new_attendance:
            logger.info(f"[EditSummaryTool] 🎉 3회 달성! attendance_count 증가: {new_attendance}일차")
        logger.info(f"[EditSummaryTool] daily_record_count 업데이트: {updated_daily_count}회")

        # 7일차 체크 (기존 nodes.py:679-702)
        current_daily_count = user_context.daily_record_count

        if current_attendance_count > 0 and current_attendance_count % 7 == 0 and current_daily_count >= 3:
            # 🚨 중요: 이미 주간요약 플래그가 있으면 제안하지 않음 (중복 방지)
            conv_state_check = await self.db.get_conversation_state(user_id)
            temp_data = conv_state_check.get("temp_data", {}) if conv_state_check else {}
            weekly_summary_ready = temp_data.get("weekly_summary_ready", False)

            if not weekly_summary_ready:
                logger.info(f"[EditSummaryTool] 🎉 7일차 달성! (수정된 요약, attendance={current_attendance_count}, daily={current_daily_count})")
                ai_response_with_suggestion = f"{ai_response}\n\n🎉 7일차 달성! 주간 요약도 보여드릴까요?"

                # 대화 저장
                await self.db.save_conversation_turn(user_id, message, ai_response_with_suggestion, is_summary=True, summary_type='daily')

                # Repository 함수로 주간 요약 플래그 설정
                await set_weekly_summary_flag(self.db, user_id, current_attendance_count, daily_session_data)

                logger.info(f"[EditSummaryTool] 수정된 요약 완료, 주간 요약은 사용자 요청 시 생성")
                return ai_response_with_suggestion
            else:
                logger.info(f"[EditSummaryTool] 7일차지만 이미 주간요약 플래그 존재 (수정) → 제안 생략")

        # 7일차 아니면 일반 수정 응답 (기존 nodes.py:704-706)
        # 대화 저장
        await self.db.save_conversation_turn(user_id, message, ai_response, is_summary=True, summary_type='daily')

        logger.info(f"[EditSummaryTool] 수정된 요약: {ai_response[:50]}...")
        return ai_response
