"""
메모리 관리: 숏텀-롱텀 전략
- 롱텀: users 테이블 (구조화 데이터) + conversations 테이블 (대화 전문)
- 숏텀: conversation_summaries (요약) + 최근 N개 (conversations에서 조회)
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import os


class MemoryManager:
    """대화 메모리 관리 (숏텀 전략)"""

    def __init__(self):
        self.recent_message_threshold = 10  # 최근 N개만 원문으로 유지
        self.summary_trigger = 20  # N개 넘으면 요약 생성
        self.cache = {}  # 임시 캐시 (비활성화됨)

    # ============================================
    # 숏텀 메모리 (대화 컨텍스트)
    # ============================================

    async def get_contextualized_history(
        self,
        user_id: str,
        database
    ) -> Dict[str, Any]:
        """
        숏텀 메모리 구성: 요약 + 최근 원문

        Returns:
            {
                "summary": "오래된 대화 요약",
                "recent_turns": [최근 10개 메시지],
                "total_count": 전체 메시지 개수,
                "summarized_count": 요약된 메시지 개수
            }
        """
        try:
            # 1️⃣ 전체 메시지 개수 확인
            total_messages = await database.count_messages(user_id)

            if total_messages == 0:
                return {
                    "summary": "",
                    "recent_turns": [],
                    "total_count": 0,
                    "summarized_count": 0
                }

            # 2️⃣ 요약 임계값 이하: 요약 없이 전부 반환
            if total_messages <= self.summary_trigger:
                all_messages = await database.get_conversation_history(
                    user_id,
                    limit=total_messages
                )
                return {
                    "summary": "",
                    "recent_turns": all_messages,
                    "total_count": total_messages,
                    "summarized_count": 0
                }

            # 3️⃣ 요약 필요: 기존 요약 확인
            summary_data = await database.get_conversation_summary(user_id)

            # 4️⃣ 요약 업데이트 필요 여부 확인
            if not summary_data or summary_data["summarized_until"] < (total_messages - self.recent_message_threshold):
                print(f"🔄 요약 업데이트 필요: {user_id}")
                summary_data = await self._update_summary(user_id, database, total_messages)
            else:
                print(f"✅ 기존 요약 사용: {user_id}")

            # 5️⃣ 최근 N개 메시지 가져오기
            recent_messages = await database.get_conversation_history(
                user_id,
                limit=self.recent_message_threshold,
                offset=total_messages - self.recent_message_threshold
            )

            return {
                "summary": summary_data["summary"],
                "recent_turns": recent_messages,
                "total_count": total_messages,
                "summarized_count": summary_data["summarized_until"]
            }

        except Exception as e:
            print(f"❌ 메모리 컨텍스트 조회 오류: {e}")
            return {
                "summary": "",
                "recent_turns": [],
                "total_count": 0,
                "summarized_count": 0
            }

    async def _update_summary(
        self,
        user_id: str,
        database,
        total_messages: int
    ) -> Dict[str, Any]:
        """요약 생성/업데이트 (LLM 직접 호출)"""
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage

        try:
            # LLM 초기화 (요약용 - 저렴한 모델)
            llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0.3,
                api_key=os.getenv("OPENAI_API_KEY")
            )

            # 1️⃣ 요약할 범위 결정 (최근 N개 제외)
            summarize_until = total_messages - self.recent_message_threshold

            # 2️⃣ 기존 요약 확인
            old_summary = await database.get_conversation_summary(user_id)

            if old_summary:
                # 기존 요약 + 새 메시지 통합 요약
                offset = old_summary["summarized_until"]
                new_message_count = summarize_until - offset

                if new_message_count > 0:
                    new_messages = await database.get_conversation_history(
                        user_id,
                        offset=offset,
                        limit=new_message_count
                    )

                    prompt = f"""이전 대화 요약:
{old_summary["summary"]}

새로운 대화:
{self._format_messages(new_messages)}

위 내용을 통합하여 3-4문장으로 요약해주세요. 핵심 주제와 사용자의 고민, 받은 조언을 중심으로."""

                else:
                    # 새 메시지 없음 (기존 요약 반환)
                    return old_summary

            else:
                # 첫 요약 생성
                messages_to_summarize = await database.get_conversation_history(
                    user_id,
                    limit=summarize_until
                )

                if not messages_to_summarize:
                    return {"summary": "", "summarized_until": 0}

                prompt = f"""다음 대화를 3-4문장으로 요약해주세요:

{self._format_messages(messages_to_summarize)}

핵심 주제와 사용자의 고민, 받은 조언을 중심으로 간결하게."""

            # 3️⃣ LLM 요약 생성
            response = await llm.ainvoke([
                SystemMessage(content="당신은 대화를 간결하게 요약하는 전문가입니다."),
                HumanMessage(content=prompt)
            ])

            new_summary = response.content.strip()

            # 4️⃣ 요약 저장
            await database.save_conversation_summary(
                user_id,
                new_summary,
                summarize_until
            )

            print(f"✅ 요약 생성 완료: {len(new_summary)}자 (메시지 {summarize_until}개까지)")

            return {
                "summary": new_summary,
                "summarized_until": summarize_until
            }

        except Exception as e:
            print(f"❌ 요약 생성 실패: {e}")
            # 실패 시 빈 요약 반환
            return {"summary": "", "summarized_until": 0}

    def _format_messages(self, messages: List[Dict]) -> str:
        """메시지 리스트를 텍스트로 포맷"""
        formatted = []
        for msg in messages:
            role = "사용자" if msg["role"] == "user" else "AI"
            formatted.append(f"{role}: {msg['content']}")
        return "\n".join(formatted)

    async def add_messages(
        self,
        user_id: str,
        user_message: str,
        ai_response: str,
        database
    ):
        """숏텀 메모리에 메시지 추가 (롱텀 DB 저장)"""
        try:
            # conversations 테이블에 영구 저장
            await database.save_message(user_id, "user", user_message)
            await database.save_message(user_id, "assistant", ai_response)

            print(f"✅ 메시지 저장 완료: {user_id}")

        except Exception as e:
            print(f"❌ 메시지 저장 실패: {e}")

    async def clear_short_term(self, user_id: str, database):
        """숏텀 메모리만 삭제 (요약만 삭제, 대화 전문은 유지)"""
        try:
            await database.delete_conversation_summary(user_id)
            print(f"🗑️ 요약 삭제 완료: {user_id}")
        except Exception as e:
            print(f"❌ 요약 삭제 실패: {e}")

    async def clear_all_memory(self, user_id: str, database):
        """모든 메모리 삭제 (주의: 대화 전문도 영구 삭제)"""
        try:
            await database.delete_conversations(user_id)
            await database.delete_conversation_summary(user_id)
            print(f"🗑️ 전체 메모리 삭제 완료: {user_id}")
        except Exception as e:
            print(f"❌ 메모리 삭제 실패: {e}")

    # ============================================
    # 기존 메서드 (호환성 유지)
    # ============================================

    async def get_conversation_history(self, user_id: str, database) -> List[Dict[str, str]]:
        """기존 코드 호환용: 전체 히스토리 조회 (deprecated)"""
        try:
            total = await database.count_messages(user_id)
            return await database.get_conversation_history(user_id, limit=total)
        except Exception as e:
            print(f"대화 히스토리 조회 오류: {e}")
            return []

    def get_cached_response(self, message: str, conversation_history: List) -> Optional[str]:
        """캐시된 응답 조회 (비활성화)"""
        return None

    def cache_response(self, message: str, conversation_history: List, response: str):
        """응답 캐싱 (비활성화)"""
        pass

    def _generate_cache_key(self, message: str, conversation_history: List) -> str:
        """캐시 키 생성 (비활성화)"""
        return ""

    async def get_user_context(self, user_id: str, database) -> Dict[str, Any]:
        """사용자 컨텍스트 조회 (롱텀 + 숏텀)"""
        try:
            # 롱텀: 사용자 정보
            user_data = await database.get_user(user_id)

            # 숏텀: 대화 컨텍스트
            conversation_context = await self.get_contextualized_history(user_id, database)

            return {
                "user_data": user_data or {},
                "conversation_summary": conversation_context["summary"],
                "recent_conversations": conversation_context["recent_turns"],
                "total_message_count": conversation_context["total_count"]
            }
        except Exception as e:
            print(f"사용자 컨텍스트 조회 오류: {e}")
            return {
                "user_data": {},
                "conversation_summary": "",
                "recent_conversations": [],
                "total_message_count": 0
            }

    def _extract_recent_topics(self, history: List[Dict]) -> List[str]:
        """최근 대화 주제 추출 (유지)"""
        topics = []
        keywords = ["프로젝트", "업무", "경력", "목표", "성과", "경험", "계획"]

        for message in history[-10:]:
            content = message.get("content", "").lower()
            for keyword in keywords:
                if keyword in content and keyword not in topics:
                    topics.append(keyword)

        return topics[:5]

    def clear_user_cache(self, user_id: str):
        """특정 사용자 캐시 삭제 (비활성화)"""
        pass
