import re
import random
import os
from typing import List, Dict, Any

# 주의: get_system_prompt, format_user_prompt 함수는 더 이상 사용되지 않음
# 새로운 온보딩 방식은 nodes.py에서 직접 EXTRACTION_SYSTEM_PROMPT를 사용함


def _format_history(history: List[Dict]) -> str:
    """대화 히스토리 포맷팅"""
    if not history:
        return "이전 대화가 없습니다."

    formatted = []
    # 최근 3개만 표시 (성능 최적화)
    recent_history = history[-3:] if len(history) > 3 else history
    for msg in recent_history:
        role = "사용자" if msg["role"] == "user" else "봇"
        content = msg["content"][:200] + "..." if len(msg["content"]) > 200 else msg["content"]
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


