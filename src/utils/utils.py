import re
import random
import os
from typing import List, Dict, Any
from langchain_openai import ChatOpenAI
from ..prompt.onboarding import ONBOARDING_SYSTEM_PROMPT, ONBOARDING_USER_PROMPT_TEMPLATE



def get_system_prompt() -> str:
    """시스템 프롬프트 반환"""
    return ONBOARDING_SYSTEM_PROMPT


def format_user_prompt(
    message: str,
    current_state: Dict,
    conversation_summary: str = "",
    conversation_history: List = None,
    target_field: str = None,
    current_attempt: int = 1
) -> str:
    """유저 프롬프트 포맷팅 (온보딩용 + 대화 컨텍스트)"""
    import json

    # current_state를 JSON 문자열로 변환
    current_state_json = json.dumps(current_state, ensure_ascii=False, indent=2)

    # 대화 히스토리 포맷팅
    formatted_history = _format_history(conversation_history) if conversation_history else "No previous conversation yet."

    # 요약 처리
    summary_text = conversation_summary if conversation_summary else "No summary yet (early conversation)."

    # 🆕 타겟 필드 정보
    target_info = f"Current target field: {target_field} (Attempt #{current_attempt})" if target_field else "All fields collected or skipped."

    # 템플릿에 모든 필드 전달
    formatted = ONBOARDING_USER_PROMPT_TEMPLATE.format(
        conversation_summary=summary_text,
        conversation_history=formatted_history,
        current_state=current_state_json,
        user_message=message[:300],  # 메시지 길이 제한
        target_field_info=target_info
    )

    return formatted


def _format_history(history: List[Dict]) -> str:
    """대화 히스토리 포맷팅"""
    if not history:
        return "이전 대화가 없습니다."

    formatted = []
    for msg in history:  # 전체 히스토리 표시
        role = "사용자" if msg["role"] == "user" else "봇"
        content = msg["content"][:300] + "..." if len(msg["content"]) > 300 else msg["content"]
        formatted.append(f"{role}: {content}")

    return "\n".join(formatted)


def simple_text_response(text: str) -> Dict[str, Any]:
    """간단한 텍스트 응답"""
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


def error_response(error_message: str) -> Dict[str, Any]:
    """에러 응답"""
    return {
        "version": "2.0",
        "template": {
            "outputs": [{
                "simpleText": {
                    "text": error_message
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


