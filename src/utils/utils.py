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
# 2. 온보딩 관련 공통 로직 (service/onboarding/onboarding_handler.py로 이동)
# -----------------------------------------------------------------------------
# - save_onboarding_conversation() → service/onboarding/onboarding_handler.py
# - update_onboarding_state() → service/onboarding/onboarding_handler.py


# -----------------------------------------------------------------------------
# 4. 7일차 체크 및 주간 요약 제안 (service/daily/record_handler.py로 이동)
# -----------------------------------------------------------------------------
# - check_and_suggest_weekly_summary() → service/daily/record_handler.py


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
# 7. 대화 저장 + 카운트 증가 통합 (service/daily/record_handler.py로 이동)
# -----------------------------------------------------------------------------
# - save_and_increment() → service/daily/record_handler.py


