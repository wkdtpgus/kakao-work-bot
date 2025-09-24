"""
간단한 LangChain 기반 챗봇 (LangGraph 없이)
"""

from typing import Dict, Any
import os
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from .utils import PromptLoader, ResponseFormatter
from .memory_manager import MemoryManager


class SimpleChatBot:
    """간단한 LangChain 기반 챗봇"""

    def __init__(self, database):
        self.db = database
        self.memory_manager = MemoryManager()
        self.prompt_loader = PromptLoader()
        self.formatter = ResponseFormatter()

        # LLM 초기화
        if os.getenv("OPENAI_API_KEY"):
            self.llm = ChatOpenAI(
                model="gpt-3.5-turbo",
                temperature=0.7,
                max_tokens=300,
                timeout=4.0
            )
        else:
            self.llm = None
            print("⚠️ OpenAI API 키가 없습니다. 모킹 모드로 실행됩니다.")

        print("✅ SimpleChatBot 초기화 완료")

    async def handle_conversation(self, user_id: str, message: str) -> Dict[str, Any]:
        """대화 처리 메인 엔트리포인트"""
        try:
            print(f"🤖 SimpleChatBot 대화 시작: {user_id}")
            print(f"📨 받은 메시지: {message}")

            # 대화 히스토리 로드
            conversation_history = await self.memory_manager.get_conversation_history(user_id, self.db)

            # AI 응답 생성
            ai_response = await self._generate_response(message, conversation_history, user_id)

            # 메모리에 저장
            await self.memory_manager.add_messages(user_id, message, ai_response, self.db)

            return self.formatter.simple_text_response(ai_response)

        except Exception as error:
            print(f"SimpleChatBot 오류: {error}")
            import traceback
            traceback.print_exc()
            return self.formatter.error_response(
                "AI 대화 처리 중 오류가 발생했습니다. 다시 시도해주세요."
            )

    async def _generate_response(self, message: str, conversation_history: list, user_id: str) -> str:
        """AI 응답 생성"""
        try:
            # 캐시 체크
            cached_response = self.memory_manager.get_cached_response(message, conversation_history)
            if cached_response:
                return cached_response

            # 모킹 모드
            if not self.llm:
                return self._get_mock_response(message)

            # 사용자 정보 가져오기
            user = await self.db.get_user(user_id)
            user_name = user.get("name", "사용자") if user else "사용자"

            # 프롬프트 구성
            system_prompt = self.prompt_loader.get_system_prompt()

            # 컨텍스트 정보 구성
            context_info = f"""
사용자 정보:
- 이름: {user_name}
- 직무: {user.get('job_title', '알 수 없음') if user else '알 수 없음'}

최근 대화: {len(conversation_history)}개 메시지
"""

            # 메시지 구성
            messages = [SystemMessage(content=system_prompt)]

            # 대화 히스토리 추가 (최근 6개만)
            limited_history = conversation_history[-6:] if len(conversation_history) > 6 else conversation_history
            for msg in limited_history:
                if msg["role"] == "user":
                    messages.append(HumanMessage(content=msg["content"][:200]))
                else:
                    messages.append(AIMessage(content=msg["content"][:200]))

            # 현재 사용자 메시지
            current_message = f"{context_info}\n\n현재 사용자 메시지: {message}"
            messages.append(HumanMessage(content=current_message))

            # LLM 호출
            response = await self.llm.ainvoke(messages)
            ai_response = response.content

            # 캐싱
            self.memory_manager.cache_response(message, conversation_history, ai_response)

            print(f"✅ AI 응답 생성: {ai_response[:50]}...")
            return ai_response

        except Exception as error:
            print(f"AI 응답 생성 오류: {error}")
            if "timeout" in str(error).lower():
                return "죄송합니다. 응답이 너무 늦어졌습니다. 다시 시도해주세요."
            return "죄송합니다. AI 응답을 생성하는 중 오류가 발생했습니다."

    def _get_mock_response(self, message: str) -> str:
        """모킹 응답 생성"""
        mock_responses = [
            "정말 흥미로운 이야기네요! 그 업무에서 어떤 부분이 가장 도전적이었나요?",
            "좋은 경험이군요! 그 결과로 어떤 성과를 얻으셨나요?",
            "흥미로운 프로젝트네요! 그 과정에서 배운 점이 있다면 무엇인가요?",
            "훌륭한 업무 경험이에요! 이런 경험을 이력서에 어떻게 표현하면 좋을까요?",
        ]

        # 키워드 기반 맞춤 응답
        if "프로젝트" in message or "개발" in message:
            return "개발 프로젝트 경험이군요! 어떤 기술 스택을 사용하셨고, 그 과정에서 어떤 도전과제가 있었나요?"
        elif "회의" in message or "미팅" in message:
            return "회의나 미팅 관련 업무네요! 그 과정에서 어떤 역할을 하셨고, 어떤 결과를 얻으셨나요?"

        import random
        return random.choice(mock_responses)