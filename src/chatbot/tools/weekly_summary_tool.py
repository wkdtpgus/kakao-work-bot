"""주간 요약 툴 - 주간 피드백 생성"""
from typing import Any
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
from ...database.user_repository import get_user_with_context
from ...database.conversation_repository import (
    get_weekly_summary_flag,
    clear_weekly_summary_flag
)
from ...database.summary_repository import prepare_weekly_feedback_data
from ...core.weekly_feedback_generator import generate_weekly_feedback
from ...core.weekly_fallback_generator import (
    calculate_current_week_day,
    format_partial_weekly_feedback,
    format_already_processed_message,
    format_no_record_message
)
import logging

logger = logging.getLogger(__name__)


class WeeklySummaryTool(BaseTool):
    """주간 피드백 생성 툴 - 기존 nodes.py:weekly_agent_node 로직 그대로"""
    name: str = "generate_weekly_feedback"
    description: str = """최근 7일간의 업무 요약을 바탕으로 주간 피드백을 생성합니다.

    입력: user_id (문자열), message (문자열)
    출력: 생성된 주간 피드백 텍스트"""
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
        """주간 피드백 생성 및 DB 저장 (Repository 함수 활용)

        호출 경로:
        1. service_router_node → 7일차 달성 후 사용자 수락 시 (weekly_acceptance)
        2. service_router_node → 사용자가 수동으로 주간 피드백 요청 (weekly_feedback)

        기존 nodes.py:881-976 로직 그대로
        """
        logger.info(f"[WeeklySummaryTool] ✅ 도구 호출됨 - user_id={user_id}, message={message[:50]}")

        try:
            # 데이터 조회
            _, user_context = await get_user_with_context(self.db, user_id)

            # Repository 함수로 주간 요약 플래그 확인 (기존 nodes.py:900-901)
            is_ready, stored_attendance_count = await get_weekly_summary_flag(self.db, user_id)

            # 7일차 자동 트리거 (플래그만 확인, daily_agent_node에서 이미 검증됨) (기존 nodes.py:903-916)
            if is_ready and stored_attendance_count:
                logger.info(f"[WeeklySummaryTool] 7일차 주간요약 생성 (attendance_count={stored_attendance_count})")

                # 주간 피드백 생성
                input_data = await prepare_weekly_feedback_data(self.db, user_id)
                output = await generate_weekly_feedback(input_data, self.llm)
                weekly_summary = output.feedback_text

                # Repository 함수로 플래그 정리
                await clear_weekly_summary_flag(self.db, user_id)

                ai_response = weekly_summary

            # 수동 요청인 경우 (7일 미달 체크) (기존 nodes.py:917-959)
            else:
                logger.info(f"[WeeklySummaryTool] 수동 요청")

                # user_context에서 attendance_count 가져오기
                current_count = user_context.attendance_count

                # 0일차: 일일기록 시작 전 (기존 nodes.py:924-930)
                if current_count == 0:
                    logger.info(f"[WeeklySummaryTool] 0일차 (일일기록 시작 전)")
                    ai_response = format_no_record_message()

                    # 일반 대화로 저장
                    await self.db.save_conversation_turn(user_id, message, ai_response, is_summary=False)

                # 1~6일차: 참고용 피드백 제공 (기존 nodes.py:932-948)
                elif current_count % 7 != 0:
                    # 현재 주차 내 일차 계산 (헬퍼 함수 사용)
                    current_day_in_week = calculate_current_week_day(current_count)
                    logger.info(f"[WeeklySummaryTool] 7일 미달 (현재 {current_day_in_week}일차) → 참고용 피드백 제공")

                    # 임시 피드백 생성
                    input_data = await prepare_weekly_feedback_data(self.db, user_id)
                    output = await generate_weekly_feedback(input_data, self.llm)
                    partial_feedback = output.feedback_text

                    # 헬퍼 함수로 응답 포맷팅
                    ai_response = format_partial_weekly_feedback(current_day_in_week, partial_feedback)

                    # 참고용은 summary_type='daily'로 저장
                    await self.db.save_conversation_turn(user_id, message, ai_response, is_summary=True, summary_type='daily')

                # 7, 14, 21일차 but 플래그 없음: 이미 확인했거나 거절한 경우 (기존 nodes.py:949-955)
                else:
                    logger.info(f"[WeeklySummaryTool] 7일차지만 플래그 없음 → 이미 처리됨")
                    ai_response = format_already_processed_message()

                    # 일반 대화로 저장
                    await self.db.save_conversation_turn(user_id, message, ai_response, is_summary=False)

                # 조기 리턴 (정식 주간요약과 분리) (기존 nodes.py:957-959)
                logger.info(f"[WeeklySummaryTool] 참고용 피드백 완료: {ai_response[:50]}...")
                return ai_response

            # 정식 주간요약 대화 저장 (is_ready=True인 경우만) (기존 nodes.py:961-962)
            await self.db.save_conversation_turn(user_id, message, ai_response, is_summary=True, summary_type='weekly')

            logger.info(f"[WeeklySummaryTool] 주간 피드백 생성 완료: {ai_response[:50]}...")

            return ai_response

        except Exception as e:
            logger.error(f"[WeeklySummaryTool] Error: {e}")
            import traceback
            traceback.print_exc()

            fallback_response = "주간 피드백 생성 중 오류가 발생했습니다."
            await self.db.save_conversation_turn(user_id, message, fallback_response, is_summary=False)

            return fallback_response
