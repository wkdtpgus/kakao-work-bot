"""
유틸리티 함수들
"""

import re
import random
from typing import List, Dict, Any


class PromptLoader:
    """프롬프트 로드 및 관리"""

    def __init__(self):
        self.system_prompt, self.user_prompt_template = self._load_prompts()

    def _load_prompts(self) -> tuple[str, str]:
        """프롬프트 파일에서 로드"""
        try:
            with open("prompt.text", "r", encoding="utf-8") as f:
                content = f.read()

            # 시스템 프롬프트 추출
            system_match = re.search(r'AI_AGENT_SYSTEM_PROMPT = """([\s\S]*?)"""', content)
            user_match = re.search(r'AI_AGENT_USER_PROMPT_TEMPLATE = """([\s\S]*?)"""', content)

            system_prompt = system_match.group(1).strip() if system_match else ""
            user_prompt_template = user_match.group(1).strip() if user_match else ""

            if system_prompt:
                print("✅ 시스템 프롬프트 로드 성공")
            if user_prompt_template:
                print("✅ 유저 프롬프트 템플릿 로드 성공")

            return system_prompt, user_prompt_template

        except Exception as e:
            print(f"❌ 프롬프트 파일 읽기 실패: {e}")
            return self._get_fallback_prompts()

    def _get_fallback_prompts(self) -> tuple[str, str]:
        """폴백 프롬프트"""
        system_prompt = """
3분커리어 AI Agent입니다.
친근하게 대화하며 업무 경험을 정리하고 강화합니다.
한국어를 사용하며, 공감 표현과 구체적 질문으로 더 나은 표현을 도출합니다.
응답은 공감→질문→정리 순서로 구성합니다.
"""

        user_template = """
# 대화 히스토리
{conversation_history}

# 사용자 최신 메시지
{user_message}

# 지시사항
위 대화 히스토리와 사용자의 최신 메시지를 바탕으로 AI_AGENT_SYSTEM_PROMPT 가이드라인에 따라 도움이 되는 응답을 제공하세요.
"""

        print("⚠️ 폴백 프롬프트 사용")
        return system_prompt.strip(), user_template.strip()

    def get_system_prompt(self) -> str:
        """시스템 프롬프트 반환"""
        return self.system_prompt

    def format_user_prompt(self, message: str, conversation_history: List[Dict]) -> str:
        """유저 프롬프트 포맷팅"""
        history_text = self._format_history(conversation_history)

        return self.user_prompt_template.format(
            conversation_history=history_text,
            user_message=message[:300]  # 메시지 길이 제한
        )

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


class TextProcessor:
    """텍스트 처리 유틸리티"""

    @staticmethod
    def extract_keywords(text: str) -> List[str]:
        """키워드 추출"""
        # 간단한 키워드 추출 (실제로는 더 정교한 NLP 사용 가능)
        keywords = []
        common_keywords = ["프로젝트", "업무", "개발", "회의", "분석", "기획", "관리", "성과", "경험"]

        for keyword in common_keywords:
            if keyword in text:
                keywords.append(keyword)

        return keywords

    @staticmethod
    def clean_user_input(text: str) -> str:
        """사용자 입력 정리"""
        # 불필요한 문구 제거
        cleaned = text.replace("입니다", "").replace("이에요", "").strip()
        return cleaned

    @staticmethod
    def extract_job_title(text: str) -> str:
        """직무명 추출"""
        return TextProcessor.clean_user_input(text)

    @staticmethod
    def extract_years(text: str) -> str:
        """연차 추출"""
        match = re.search(r'(\d+)년차?', text)
        return match.group(1) + "년차" if match else text

    @staticmethod
    def truncate_text(text: str, max_length: int = 200) -> str:
        """텍스트 길이 제한"""
        return text[:max_length] + "..." if len(text) > max_length else text