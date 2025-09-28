import re
import random
import os
from typing import List, Dict, Any
from langchain_openai import ChatOpenAI
from ..prompt.onboarding import ONBOARDING_SYSTEM_PROMPT, ONBOARDING_USER_PROMPT_TEMPLATE


class PromptLoader:
    """프롬프트 로드 및 관리"""

    def __init__(self):
        self.system_prompt = ONBOARDING_SYSTEM_PROMPT
        self.user_prompt_template = ONBOARDING_USER_PROMPT_TEMPLATE

        print("✅ 온보딩 프롬프트 로드 성공")

    def get_system_prompt(self) -> str:
        """시스템 프롬프트 반환"""
        return self.system_prompt

    def format_user_prompt(self, message: str, current_state: Dict) -> str:
        """유저 프롬프트 포맷팅 (온보딩용)"""
        # current_state를 JSON 문자열로 변환
        import json
        current_state_json = json.dumps(current_state, ensure_ascii=False, indent=2)

        formatted = self.user_prompt_template.format(
            current_state=current_state_json,
            user_message=message[:300]  # 메시지 길이 제한
        )
        print(f"🔍 포맷된 프롬프트:\n{formatted}")
        return formatted

    def _format_history(self, history: List[Dict]) -> str:
        """대화 히스토리 포맷팅"""
        if not history:
            return "이전 대화가 없습니다."

        formatted = []
        for msg in history[-6:]:  # 최근 6개만
            role = "사용자" if msg["role"] == "user" else "봇"
            content = msg["content"][:200] + "..." if len(msg["content"]) > 200 else msg["content"]
            formatted.append(f"{role}: {content}")

        return "\n".join(formatted)


class ResponseFormatter:
    """응답 포맷팅"""

    @staticmethod
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

    @staticmethod
    def quick_reply_response(text: str, quick_replies: List[Dict[str, str]]) -> Dict[str, Any]:
        """빠른 답변 포함 응답"""
        return {
            "version": "2.0",
            "template": {
                "outputs": [{
                    "simpleText": {
                        "text": text
                    }
                }],
                "quickReplies": quick_replies
            }
        }

    @staticmethod
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

    @staticmethod
    def get_thinking_response() -> Dict[str, Any]:
        """생각 중 응답 (즉시 응답용)"""
        thinking_messages = [
            "음... 🤔 그건 정말 흥미로운 주제네요! 잠깐 생각해볼게요.",
            "아, 그런 질문이군요! 좀 더 구체적으로 생각해보겠습니다.",
            "흠... 🤔 그 부분에 대해 좀 더 깊이 생각해보고 있어요.",
            "오, 좋은 지적이에요! 잠시 정리해보겠습니다.",
            "그건 정말 중요한 포인트네요. 차근차근 정리해볼게요.",
        ]

        return ResponseFormatter.simple_text_response(random.choice(thinking_messages))




# =============================================================================
# 온보딩 관련 헬퍼 함수들
# =============================================================================

def is_onboarding_complete(current_state: Dict[str, Any]) -> bool:
    """온보딩 완료 여부 체크"""
    required_fields = [
        "name", "job", "total_experience_year", "job_experience_year",
        "career_goal", "projects", "recent_tasks", "job_meaning", "work_philosophy"
    ]

    return all(current_state.get(field) is not None for field in required_fields)


async def get_daily_reflections_count(user_id: str, db) -> int:
    """사용자의 일일 회고 개수 조회"""
    try:
        # TODO: 실제 DB에서 일일 회고 개수 조회
        # 임시로 0 반환
        return 0
    except Exception as e:
        print(f"❌ 일일 회고 개수 조회 실패: {e}")
        return 0


# =============================================================================
# 모델 로딩 함수들
# =============================================================================

# 모델 초기화 (lazy loading)
def get_openai_model():
    """OpenAI 모델 가져오기 (lazy loading)"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OpenAI API 키가 필요합니다. 환경변수 OPENAI_API_KEY를 설정해주세요.")

    return ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.7,
        max_tokens=300,
        timeout=4.0
    )