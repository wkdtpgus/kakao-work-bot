"""
메모리 및 대화 히스토리 관리
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import json


class MemoryManager:
    """대화 메모리 및 히스토리 관리"""

    def __init__(self):
        self.cache = {}
        self.cache_ttl = 5 * 60  # 5분

    async def get_conversation_history(self, user_id: str, database) -> List[Dict[str, str]]:
        """대화 히스토리 조회"""
        try:
            state = await database.get_conversation_state(user_id)
            if state and state.get("temp_data"):
                return state["temp_data"].get("conversation_history", [])
            return []
        except Exception as e:
            print(f"대화 히스토리 조회 오류: {e}")
            return []

    async def add_messages(self, user_id: str, user_message: str, ai_response: str, database):
        """대화에 새 메시지 추가"""
        try:
            # 기존 히스토리 가져오기
            current_history = await self.get_conversation_history(user_id, database)

            # 새 메시지 추가
            updated_history = current_history + [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": ai_response}
            ]

            # 히스토리 길이 제한 (최근 20개 메시지만 유지)
            if len(updated_history) > 20:
                updated_history = updated_history[-20:]

            # DB 업데이트
            state = await database.get_conversation_state(user_id)
            temp_data = state.get("temp_data", {}) if state else {}
            temp_data["conversation_history"] = updated_history

            await database.update_conversation_state(
                user_id,
                state.get("current_step", "ai_conversation") if state else "ai_conversation",
                temp_data
            )

            print(f"✅ 대화 메모리 업데이트: {len(updated_history)}개 메시지")

        except Exception as e:
            print(f"❌ 메모리 업데이트 오류: {e}")

    def get_cached_response(self, message: str, conversation_history: List) -> Optional[str]:
        """캐시된 응답 조회 (임시로 비활성화)"""
        # 온보딩 중에는 캐시 사용하지 않음
        return None

    def cache_response(self, message: str, conversation_history: List, response: str):
        """응답 캐싱"""
        cache_key = self._generate_cache_key(message, conversation_history)

        self.cache[cache_key] = {
            "response": response,
            "timestamp": datetime.now().timestamp()
        }

        # 캐시 크기 제한
        if len(self.cache) > 100:
            oldest_key = min(self.cache.keys(),
                           key=lambda k: self.cache[k]["timestamp"])
            del self.cache[oldest_key]

    def _generate_cache_key(self, message: str, conversation_history: List) -> str:
        """캐시 키 생성"""
        history_hash = hash(json.dumps(conversation_history, sort_keys=True))
        return f"{message[:50]}_{len(conversation_history)}_{history_hash}"

    async def get_user_context(self, user_id: str, database) -> Dict[str, Any]:
        """사용자 컨텍스트 조회"""
        try:
            user_data = await database.get_user(user_id)
            conversation_history = await self.get_conversation_history(user_id, database)

            return {
                "user_data": user_data or {},
                "conversation_history": conversation_history,
                "recent_topics": self._extract_recent_topics(conversation_history)
            }
        except Exception as e:
            print(f"사용자 컨텍스트 조회 오류: {e}")
            return {"user_data": {}, "conversation_history": [], "recent_topics": []}

    def _extract_recent_topics(self, history: List[Dict]) -> List[str]:
        """최근 대화 주제 추출"""
        topics = []
        keywords = ["프로젝트", "업무", "경력", "목표", "성과", "경험", "계획"]

        for message in history[-10:]:  # 최근 10개 메시지
            content = message.get("content", "").lower()
            for keyword in keywords:
                if keyword in content and keyword not in topics:
                    topics.append(keyword)

        return topics[:5]  # 최대 5개

    def clear_user_cache(self, user_id: str):
        """특정 사용자 캐시 삭제"""
        keys_to_delete = [key for key in self.cache.keys() if user_id in key]
        for key in keys_to_delete:
            del self.cache[key]

        print(f"🗑️ 사용자 {user_id} 캐시 삭제: {len(keys_to_delete)}개")