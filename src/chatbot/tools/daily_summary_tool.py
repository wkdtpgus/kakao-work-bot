"""일일 요약 툴 - 오늘 업무 요약 생성"""
from typing import Any
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
from ...database.user_repository import (
    increment_counts_with_check,
    get_user_with_context
)
from ...core.summary_generator import generate_daily_summary
from ...core.schemas import DailySummaryInput
import logging

logger = logging.getLogger(__name__)


class DailySummaryTool(BaseTool):
    """일일 요약 생성 툴"""
    name: str = "generate_daily_summary"
    description: str = """오늘의 업무 대화를 요약합니다.

    입력: user_id (문자열), message (문자열)
    출력: 생성된 요약 텍스트"""
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
        """일일 요약 생성 - 기존 nodes.py:708-764 로직 그대로"""
        from datetime import datetime
        from ...database.summary_repository import prepare_daily_summary_data
        from ...database.conversation_repository import set_weekly_summary_flag

        logger.info(f"[DailySummaryTool] ✅ 도구 호출됨 - user_id={user_id}, message={message[:50]}")

        # 데이터 조회
        _, user_context = await get_user_with_context(self.db, user_id)

        # 🚨 중요: 요약 생성 시에만 오늘 전체 대화 조회 (기존 nodes.py:712-714)
        today = datetime.now().date().isoformat()
        all_today_turns = await self.db.get_conversation_history_by_date_v2(user_id, today, limit=50)
        logger.info(f"[DailySummaryTool] 요약용 전체 대화 조회: {len(all_today_turns)}턴")

        # 요약 생성 (기존 nodes.py:716-720)
        input_data = await prepare_daily_summary_data(self.db, user_id, all_today_turns)
        output = await generate_daily_summary(input_data, self.llm)
        ai_response = output.summary_text
        current_attendance_count = input_data.attendance_count

        # 요약 플래그 설정 (기존 로직)
        is_summary_response = True
        summary_type_value = 'daily'

        # last_summary_at 플래그 저장 + conversation_count 리셋 (기존 nodes.py:726-729)
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
        logger.info(f"[DailySummaryTool] 요약 생성 완료 → conversation_count 리셋")

        # 7일차 체크 (기존 nodes.py:731-760)
        current_daily_count = user_context.daily_record_count

        if current_attendance_count > 0 and current_attendance_count % 7 == 0 and current_daily_count >= 3:
            # 🚨 중요: 이미 주간요약 플래그가 있으면 제안하지 않음 (중복 방지)
            conv_state_check = await self.db.get_conversation_state(user_id)
            temp_data = conv_state_check.get("temp_data", {}) if conv_state_check else {}
            weekly_summary_ready = temp_data.get("weekly_summary_ready", False)

            if not weekly_summary_ready:
                logger.info(f"[DailySummaryTool] 🎉 7일차 달성! (attendance={current_attendance_count}, daily={current_daily_count})")
                ai_response_with_suggestion = f"{ai_response}\n\n🎉 7일차 달성! 주간 요약도 보여드릴까요?"

                # 대화 저장
                await self.db.save_conversation_turn(user_id, message, ai_response_with_suggestion, is_summary=True, summary_type='daily')

                # Repository 함수로 주간 요약 플래그 설정 (기존 로직)
                await set_weekly_summary_flag(self.db, user_id, current_attendance_count, daily_session_data)

                logger.info(f"[DailySummaryTool] 데일리 요약 완료, 주간 요약은 사용자 요청 시 생성")

                return ai_response_with_suggestion
            else:
                logger.info(f"[DailySummaryTool] 7일차지만 이미 주간요약 플래그 존재 → 제안 생략")

        # 7일차 아니면 일반 요약 응답
        # 대화 저장 (기존 nodes.py:747)
        await self.db.save_conversation_turn(user_id, message, ai_response, is_summary=True, summary_type='daily')

        return ai_response
