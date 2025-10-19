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
        self.recent_message_threshold = 3  # 최근 N개만 원문으로 유지 (성능 최적화)
        self.summary_trigger = 10  # N개 넘으면 요약 생성
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
        숏텀 메모리 구성: 요약 + 최근 5개 턴 (V2 스키마)

        Returns:
            {
                "summary": "오래된 대화 요약",
                "recent_turns": [최근 5개 턴을 role/content 형식으로 변환],
                "total_count": 전체 턴 개수,
                "summarized_count": 요약된 턴 개수
            }
        """
        try:
            # 1️⃣ V2: 최근 5개 턴 조회 (숏텀 메모리 뷰 사용)
            recent_turns_v2 = await database.get_shortterm_memory_v2(user_id)

            # V2 형식 {"user": "...", "ai": "..."} → role/content 형식으로 변환
            recent_messages = []
            for turn in reversed(recent_turns_v2):  # 오래된 순으로 변환
                recent_messages.append({"role": "user", "content": turn.get("user", "")})
                recent_messages.append({"role": "assistant", "content": turn.get("ai", "")})

            # 2️⃣ 전체 턴 개수 확인 (최근 100개 조회해서 카운트)
            all_recent_turns = await database.get_recent_turns_v2(user_id, limit=100)
            total_turns = len(all_recent_turns)

            # 3️⃣ 요약 임계값 체크 (5개 턴 = 10개 메시지)
            if total_turns <= 5:
                # 요약 불필요: 최근 5개 턴만 반환
                return {
                    "summary": "",
                    "recent_turns": recent_messages,
                    "total_count": total_turns * 2,  # 턴 → 메시지 개수
                    "summarized_count": 0
                }

            # 4️⃣ 요약 필요: 기존 요약 확인
            summary_data = await database.get_conversation_summary(user_id)

            # 5️⃣ 요약 업데이트 필요 여부 확인
            if not summary_data or summary_data["summarized_until"] < (total_turns - 5) * 2:
                print(f"🔄 [V2] 요약 업데이트 필요: {user_id}")
                summary_data = await self._update_summary_v2(user_id, database, all_recent_turns)
            else:
                print(f"✅ [V2] 기존 요약 사용: {user_id}")

            return {
                "summary": summary_data.get("summary", ""),
                "recent_turns": recent_messages,
                "total_count": total_turns * 2,
                "summarized_count": summary_data.get("summarized_until", 0)
            }

        except Exception as e:
            print(f"❌ [V2] 메모리 컨텍스트 조회 오류: {e}")
            return {
                "summary": "",
                "recent_turns": [],
                "total_count": 0,
                "summarized_count": 0
            }

    async def _update_summary_v2(
        self,
        user_id: str,
        database,
        all_recent_turns: list
    ) -> Dict[str, Any]:
        """요약 생성/업데이트 (V2 스키마 - LLM 직접 호출)"""
        from langchain_core.messages import HumanMessage, SystemMessage
        from ..utils.models import SUMMARY_MODEL_CONFIG
        from langchain_openai import ChatOpenAI

        try:
            # 요약용 LLM 생성 (API 키 포함)
            llm = ChatOpenAI(**SUMMARY_MODEL_CONFIG, api_key=os.getenv("OPENAI_API_KEY"))

            total_turns = len(all_recent_turns)

            # 1️⃣ 요약할 범위 결정 (최근 5개 턴 제외)
            summarize_until_turns = total_turns - 5
            summarize_until_messages = summarize_until_turns * 2  # 턴 → 메시지

            # 2️⃣ 기존 요약 확인
            old_summary = await database.get_conversation_summary(user_id)

            if old_summary:
                # 기존 요약 + 새 턴 통합 요약
                already_summarized = old_summary["summarized_until"]  # 메시지 개수
                already_summarized_turns = already_summarized // 2  # 턴 개수

                new_turn_count = summarize_until_turns - already_summarized_turns

                if new_turn_count > 0:
                    # 새로 요약할 턴들만 가져오기 (역순이므로 뒤에서부터)
                    new_turns = all_recent_turns[-(already_summarized_turns + new_turn_count):-5]

                    # 턴 형식 → role/content 형식으로 변환
                    new_messages = []
                    for turn in new_turns:
                        new_messages.append({"role": "user", "content": turn.get("user_message", "")})
                        new_messages.append({"role": "assistant", "content": turn.get("ai_message", "")})

                    prompt = f"""이전 대화 요약:
{old_summary["summary"]}

새로운 대화:
{self._format_messages(new_messages)}

위 내용을 통합하여 3-4문장으로 요약해주세요. 핵심 주제와 사용자의 고민, 받은 조언을 중심으로."""

                else:
                    # 새 턴 없음 (기존 요약 반환)
                    return old_summary

            else:
                # 첫 요약 생성
                turns_to_summarize = all_recent_turns[:-5] if total_turns > 5 else []

                if not turns_to_summarize:
                    return {"summary": "", "summarized_until": 0}

                # 턴 형식 → role/content 형식으로 변환
                messages_to_summarize = []
                for turn in turns_to_summarize:
                    messages_to_summarize.append({"role": "user", "content": turn.get("user_message", "")})
                    messages_to_summarize.append({"role": "assistant", "content": turn.get("ai_message", "")})

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
                summarize_until_messages
            )

            print(f"✅ [V2] 요약 생성 완료: {len(new_summary)}자 (턴 {summarize_until_turns}개 / 메시지 {summarize_until_messages}개까지)")

            return {
                "summary": new_summary,
                "summarized_until": summarize_until_messages
            }

        except Exception as e:
            print(f"❌ [V2] 요약 생성 실패: {e}")
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
            # V2 스키마: 대화 턴 단위로 저장
            result = await database.save_conversation_turn(
                user_id,
                user_message,
                ai_response,
                is_summary=False  # 일반 대화
            )

            if result:
                print(f"✅ [V2] 대화 턴 저장 완료: {user_id} - 턴 #{result['turn_index']}")
            else:
                print(f"❌ [V2] 대화 턴 저장 실패: {user_id}")

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

    async def get_conversation_history(self, user_id: str, database, limit: int = 10) -> List[Dict[str, str]]:
        """대화 히스토리 조회 (V2 스키마)"""
        try:
            # V2: LLM용 히스토리 변환 (role/content 형식)
            return await database.get_conversation_history_for_llm_v2(user_id, limit=limit)
        except Exception as e:
            print(f"❌ [V2] 대화 히스토리 조회 오류: {e}")
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
            user = await database.get_user(user_id)
            user_data = user.dict() if user else {}

            # 숏텀: 대화 컨텍스트
            conversation_context = await self.get_contextualized_history(user_id, database)

            return {
                "user_data": user_data,
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
