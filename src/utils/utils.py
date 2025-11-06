import re
import random
import os
from typing import List, Dict, Any, Optional, Type, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# 주의: get_system_prompt, format_user_prompt 함수는 더 이상 사용되지 않음
# 새로운 온보딩 방식은 nodes.py에서 직접 EXTRACTION_SYSTEM_PROMPT를 사용함

def simple_text_response(text: str) -> Dict[str, Any]:
    """간단한 텍스트 응답 (카카오톡 API 포맷)"""
    return {
        "version": "2.0",
        "template": {
            "outputs": [{
                "simpleText": {
                    "text": text
                }
            }]
        }
    }




# =============================================================================
# 온보딩 관련 헬퍼 함수들
# =============================================================================

def is_onboarding_complete(current_state: Dict[str, Any]) -> bool:
    """온보딩 완료 여부 체크"""
    required_fields = [
        "name", "job_title", "total_years", "job_years",
        "career_goal", "project_name", "recent_work", "job_meaning", "important_thing"
    ]

    return all(current_state.get(field) is not None for field in required_fields)


# =============================================================================
# Nodes.py에서 추출한 재사용 가능한 헬퍼 함수들
# =============================================================================

# -----------------------------------------------------------------------------
# 1. 대화 히스토리 처리 관련
# -----------------------------------------------------------------------------
# Note: extract_last_bot_message, enhance_message_with_context는
# src/service/router/message_enhancer.py로 이동되었습니다.


def format_conversation_history(
    messages: List[Dict[str, str]],
    max_turns: int = 3,
    role_key: str = "role",
    content_key: str = "content"
) -> str:
    """
    대화 히스토리를 텍스트로 포맷팅

    Args:
        messages: [{"role": "assistant"|"user", "content": "..."}, ...] 형식
        max_turns: 최근 N턴만 포함 (기본 3턴)
        role_key: role 키 이름
        content_key: content 키 이름

    Returns:
        포맷팅된 대화 히스토리 문자열

    Usage:
        온보딩 LLM 프롬프트 생성 시 컨텍스트 제공
    """
    if not messages:
        return "(첫 메시지)"

    recent_messages = messages[-max_turns * 2:] if len(messages) > max_turns * 2 else messages

    history_lines = []
    for msg in recent_messages:
        role = "봇" if msg.get(role_key) == "assistant" else "사용자"
        content = msg.get(content_key, "")
        history_lines.append(f"{role}: {content}")

    return "\n".join(history_lines) if history_lines else "(첫 메시지)"


# -----------------------------------------------------------------------------
# 2. 온보딩 관련 공통 로직
# -----------------------------------------------------------------------------

async def save_onboarding_conversation(
    db,
    user_id: str,
    user_message: str,
    ai_message: str,
    max_history: int = 6
) -> None:
    """
    온보딩 대화 히스토리 저장 (최근 N개만 유지)

    Args:
        db: Database 인스턴스
        user_id: 사용자 ID
        user_message: 사용자 메시지
        ai_message: AI 응답 메시지
        max_history: 최대 유지 턴 수 (기본 6개 = 3턴)

    Usage:
        onboarding_agent_node에서 대화 진행 중 히스토리 저장
    """
    conv_state = await db.get_conversation_state(user_id)
    recent_messages = []

    if conv_state and conv_state.get("temp_data"):
        recent_messages = conv_state["temp_data"].get("onboarding_messages", [])[-max_history:]

    recent_messages.append({"role": "user", "content": user_message})
    recent_messages.append({"role": "assistant", "content": ai_message})
    recent_messages = recent_messages[-max_history:]  # 최근 N개만 유지

    await db.upsert_conversation_state(
        user_id,
        current_step="onboarding",
        temp_data={"onboarding_messages": recent_messages}
    )


async def update_onboarding_state(
    db,
    user_id: str,
    metadata,  # UserMetadata 타입
    ai_response: str,
    user_message: Optional[str] = None
) -> None:
    """
    온보딩 메타데이터 + 대화 히스토리 업데이트를 한 번에 처리

    Args:
        db: Database 인스턴스
        user_id: 사용자 ID
        metadata: UserMetadata 객체
        ai_response: AI 응답 메시지
        user_message: 사용자 메시지 (있으면 히스토리에 추가)

    Usage:
        onboarding_agent_node에서 메타데이터 저장 + 히스토리 저장을 한 번에
    """
    from ..database import save_onboarding_metadata

    # 메타데이터 저장
    await save_onboarding_metadata(db, user_id, metadata)

    # 대화 히스토리 저장 (user_message가 있을 때만)
    if user_message:
        await save_onboarding_conversation(db, user_id, user_message, ai_response)


# -----------------------------------------------------------------------------
# 4. 7일차 체크 및 주간 요약 제안 (핵심 중복 로직)
# -----------------------------------------------------------------------------

async def check_and_suggest_weekly_summary(
    db,
    user_id: str,
    user_context,  # UserContext 타입
    current_attendance_count: int,
    ai_response: str,
    message: str,
    is_summary: bool = True,
    summary_type: str = 'daily'
) -> Tuple[str, bool]:
    """
    7일차 달성 시 주간 요약 제안 로직 (중복 제거용)

    Args:
        db: Database 인스턴스
        user_id: 사용자 ID
        user_context: UserContext 객체
        current_attendance_count: 현재 출석 일수
        ai_response: 기본 AI 응답 (요약 텍스트 등)
        message: 사용자 메시지
        is_summary: 요약 응답 여부
        summary_type: 요약 타입 ('daily' 등)

    Returns:
        (ai_response_with_suggestion, should_suggest_weekly)
        - ai_response_with_suggestion: 주간 요약 제안 포함 응답
        - should_suggest_weekly: 주간 요약 제안 여부 (True/False)

    Usage:
        daily_agent_node에서 요약 생성/수정 후 7일차 체크
    """
    from ..database import set_weekly_summary_flag
    from ..config.business_config import DAILY_TURNS_THRESHOLD, WEEKLY_CYCLE_DAYS

    current_daily_count = user_context.daily_record_count

    # 주간 요약 주기 체크 (7, 14, 21일차 등)
    if current_attendance_count > 0 and current_attendance_count % WEEKLY_CYCLE_DAYS == 0 and current_daily_count >= DAILY_TURNS_THRESHOLD:
        # 중복 방지: 이미 주간요약 플래그가 있거나 이미 완료했으면 제안하지 않음
        conv_state = await db.get_conversation_state(user_id)
        temp_data = conv_state.get("temp_data", {}) if conv_state else {}
        weekly_summary_ready = temp_data.get("weekly_summary_ready", False)

        # 이번 주차에 주간요약을 이미 완료했는지 체크 (주차 단위 비교)
        weekly_completed_at_count = temp_data.get("weekly_completed_at_count")
        if weekly_completed_at_count:
            # 주차 번호로 비교 (1~7일차: 1주차, 8~14일차: 2주차, ...)
            current_week = (current_attendance_count - 1) // 7 + 1
            completed_week = (weekly_completed_at_count - 1) // 7 + 1
            already_completed_this_week = (current_week == completed_week)
        else:
            already_completed_this_week = False

        if not weekly_summary_ready and not already_completed_this_week:
            logger.info(f"[check_weekly_summary] 🎉 7일차 달성! (attendance={current_attendance_count}, daily={current_daily_count})")

            # 주간 요약 제안 메시지 추가
            ai_response_with_suggestion = f"{ai_response}\n\n🎉 7일차 달성! 주간 요약도 보여드릴까요?"

            # 대화 저장
            await db.save_conversation_turn(
                user_id,
                message,
                ai_response_with_suggestion,
                is_summary=is_summary,
                summary_type=summary_type
            )

            # 주간 요약 플래그 설정
            await set_weekly_summary_flag(db, user_id, current_attendance_count, user_context.daily_session_data)

            return ai_response_with_suggestion, True
        else:
            if weekly_summary_ready:
                logger.info(f"[check_weekly_summary] 7일차지만 이미 주간요약 플래그 존재 → 제안 생략")
            elif already_completed_this_week:
                logger.info(f"[check_weekly_summary] 7일차지만 이미 주간요약 완료 (completed_at={weekly_completed_at_count}) → 제안 생략")
            # 플래그가 이미 있거나 완료되었으면 일반 요약으로 처리 (제안 없이)
            return ai_response, False

    # 7일차 아님
    return ai_response, False


# -----------------------------------------------------------------------------
# 5. Command 응답 생성 헬퍼
# -----------------------------------------------------------------------------

def error_command(error_message: str = "처리 중 오류가 발생했습니다.", goto: str = "__end__"):
    """
    에러 응답 Command 생성

    Args:
        error_message: 에러 메시지
        goto: 이동할 노드 (기본값: "__end__")

    Returns:
        Command 객체

    Usage:
        모든 노드에서 에러 처리 시 통일된 응답
    """
    from langgraph.types import Command
    return Command(update={"ai_response": error_message}, goto=goto)


def success_command(ai_response: str, user_context=None, goto: str = "__end__"):
    """
    성공 응답 Command 생성 (user_context 업데이트 포함)

    Args:
        ai_response: AI 응답 메시지
        user_context: UserContext 객체 (있으면 함께 업데이트)
        goto: 이동할 노드 (기본값: "__end__")

    Returns:
        Command 객체

    Usage:
        모든 노드에서 정상 응답 시 통일된 응답
    """
    from langgraph.types import Command

    updates = {"ai_response": ai_response}
    if user_context is not None:
        updates["user_context"] = user_context

    return Command(update=updates, goto=goto)


# -----------------------------------------------------------------------------
# 6. 세션 데이터 관리
# -----------------------------------------------------------------------------

def reset_session_data(user_context) -> None:
    """
    daily_session_data를 빈 딕셔너리로 초기화

    Args:
        user_context: UserContext 객체

    Usage:
        대화 거절, 종료, 재시작 시 세션 초기화
    """
    user_context.daily_session_data = {}


# -----------------------------------------------------------------------------
# 7. 대화 저장 + 카운트 증가 통합
# -----------------------------------------------------------------------------

async def save_and_increment(
    db,
    user_id: str,
    user_message: str,
    ai_response: str,
    user_context,  # UserContext 타입
    is_summary: bool = False,
    summary_type: Optional[str] = None,
    should_increment: bool = True
) -> Tuple[int, Optional[int]]:
    """
    대화 저장 + daily_record_count 증가를 한 번에 처리

    Args:
        db: Database 인스턴스
        user_id: 사용자 ID
        user_message: 사용자 메시지
        ai_response: AI 응답 메시지
        user_context: UserContext 객체
        is_summary: 요약 응답 여부
        summary_type: 요약 타입 ('daily' 또는 'weekly')
        should_increment: 카운트 증가 여부 (요약 생성 시에는 False)

    Returns:
        (updated_daily_count, new_attendance)
        - updated_daily_count: 업데이트된 daily_record_count
        - new_attendance: 5회 달성 시 새로운 출석 일수 (아니면 None)

    Usage:
        daily_agent_node에서 대화 저장 + 카운트 증가 로직 통합
    """
    from ..database import increment_counts_with_check

    # 대화 저장
    await db.save_conversation_turn(
        user_id,
        user_message,
        ai_response,
        is_summary=is_summary,
        summary_type=summary_type if is_summary else None
    )

    # 카운트 증가 (필요 시)
    if should_increment:
        updated_daily_count, new_attendance = await increment_counts_with_check(db, user_id)

        if new_attendance:
            logger.info(f"[save_and_increment] 🎉 5회 달성! attendance_count 증가: {new_attendance}일차")
            user_context.attendance_count = new_attendance

        logger.info(f"[save_and_increment] daily_record_count 업데이트: {updated_daily_count}회")
        return updated_daily_count, new_attendance
    else:
        # 카운트 증가 안 함 (현재 값 유지)
        logger.info(f"[save_and_increment] 요약 생성 - daily_record_count 증가 안 함")
        return user_context.daily_record_count, None


