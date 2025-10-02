import os
from supabase import create_client, Client
from typing import Optional, Dict, Any
from datetime import datetime

class Database:
    def __init__(self):
        # Supabase 클라이언트 설정
        if os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_ANON_KEY"):
            self.supabase: Client = create_client(
                os.getenv("SUPABASE_URL"),
                os.getenv("SUPABASE_ANON_KEY")
            )
            print("✅ Supabase 클라이언트 초기화 성공")
        else:
            print("⚠️ Supabase 환경 변수가 설정되지 않았습니다. 모킹 모드로 실행됩니다.")
            self.supabase = None

        # 모킹 데이터 저장소 (실제 DB 없을 때 사용)
        self._mock_users = {}
        self._mock_states = {}

    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """사용자 정보 조회"""
        if not self.supabase:
            return self._mock_users.get(user_id)

        try:
            response = self.supabase.table("users").select("*").eq("kakao_user_id", user_id).single().execute()
            return response.data if response.data else None
        except Exception as e:
            if "PGRST116" in str(e):  # 데이터 없음
                return None
            print(f"사용자 조회 오류: {e}")
            return None

    async def create_or_update_user(self, user_id: str, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """사용자 생성 또는 업데이트"""
        if not self.supabase:
            self._mock_users[user_id] = {**user_data, "kakao_user_id": user_id}
            return self._mock_users[user_id]

        try:
            user_data["kakao_user_id"] = user_id
            response = self.supabase.table("users").upsert(
                user_data,
                on_conflict="kakao_user_id"
            ).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"사용자 생성/업데이트 오류: {e}")
            raise e

    async def get_conversation_state(self, user_id: str) -> Optional[Dict[str, Any]]:
        """대화 상태 조회"""
        if not self.supabase:
            return self._mock_states.get(user_id)

        try:
            print(f"🔍 [DB] get 시도 - user_id: {user_id}")
            response = self.supabase.table("conversation_states").select("*").eq("kakao_user_id", user_id).single().execute()
            print(f"✅ [DB] get 성공 - data: {response.data}")
            return response.data if response.data else None
        except Exception as e:
            if "PGRST116" in str(e):  # 데이터 없음
                print(f"⚠️ [DB] 데이터 없음 (PGRST116)")
                return None
            print(f"❌ [DB] 대화 상태 조회 오류: {e}")
            return None

    async def upsert_conversation_state(self, user_id: str, current_step: str, temp_data: Dict[str, Any]) -> Dict[str, Any]:
        """대화 상태 생성 또는 업데이트"""
        if not self.supabase:
            self._mock_states[user_id] = {
                "kakao_user_id": user_id,
                "current_step": current_step,
                "temp_data": temp_data,
                "updated_at": datetime.now().isoformat()
            }
            return self._mock_states[user_id]

        try:
            state_data = {
                "kakao_user_id": user_id,
                "current_step": current_step,
                "temp_data": temp_data,
                "updated_at": datetime.now().isoformat()
            }
            print(f"💾 [DB] upsert 시도 - user_id: {user_id}, current_step: {current_step}, temp_data keys: {list(temp_data.keys())}")
            response = self.supabase.table("conversation_states").upsert(
                state_data,
                on_conflict="kakao_user_id"
            ).execute()
            print(f"✅ [DB] upsert 성공 - response: {response.data}")
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"❌ [DB] 대화 상태 생성/업데이트 오류: {e}")
            import traceback
            traceback.print_exc()
            raise e

    async def update_conversation_state(self, user_id: str, current_step: str, temp_data: Dict[str, Any]) -> Dict[str, Any]:
        """대화 상태 업데이트"""
        if not self.supabase:
            if user_id in self._mock_states:
                self._mock_states[user_id].update({
                    "current_step": current_step,
                    "temp_data": temp_data,
                    "updated_at": datetime.now().isoformat()
                })
            return self._mock_states.get(user_id)

        try:
            state_data = {
                "current_step": current_step,
                "temp_data": temp_data,
                "updated_at": datetime.now().isoformat()
            }
            response = self.supabase.table("conversation_states").update(state_data).eq("kakao_user_id", user_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"대화 상태 업데이트 오류: {e}")
            raise e

    async def delete_conversation_state(self, user_id: str) -> bool:
        """대화 상태 삭제"""
        if not self.supabase:
            if user_id in self._mock_states:
                del self._mock_states[user_id]
                return True
            return False

        try:
            self.supabase.table("conversation_states").delete().eq("kakao_user_id", user_id).execute()
            return True
        except Exception as e:
            print(f"대화 상태 삭제 오류: {e}")
            return False

    async def test_connection(self) -> bool:
        """데이터베이스 연결 테스트"""
        if not self.supabase:
            print("⚠️ 모킹 모드에서 실행 중입니다.")
            return True

        try:
            # users 테이블에 간단한 쿼리 수행
            response = self.supabase.table("users").select("count").limit(1).execute()
            print("✅ Supabase 연결 성공!")
            return True
        except Exception as e:
            print(f"❌ Supabase 연결 실패: {e}")
            return False

    # ============================================
    # 메모리 관리 메서드 (conversations 테이블)
    # ============================================

    async def save_message(self, user_id: str, role: str, content: str) -> bool:
        """대화 메시지 저장 (롱텀 메모리) - ai_conversations 테이블 활용"""
        if not self.supabase:
            # Mock 모드: 메모리에만 저장
            if not hasattr(self, '_mock_conversations'):
                self._mock_conversations = []
            self._mock_conversations.append({
                "user_id": user_id,
                "role": role,
                "content": content,
                "created_at": datetime.now().isoformat()
            })
            return True

        try:
            # 1. 기존 대화 가져오기
            response = self.supabase.table("ai_conversations") \
                .select("conversation_history") \
                .eq("kakao_user_id", user_id) \
                .execute()

            # 2. 대화 히스토리 구성
            if response.data and len(response.data) > 0:
                history = response.data[0].get("conversation_history", [])
            else:
                history = []

            # 3. 새 메시지 추가
            history.append({
                "role": role,
                "content": content,
                "created_at": datetime.now().isoformat()
            })

            # 4. 저장 (upsert)
            self.supabase.table("ai_conversations").upsert({
                "kakao_user_id": user_id,
                "conversation_history": history,
                "updated_at": datetime.now().isoformat()
            }).execute()

            return True
        except Exception as e:
            print(f"메시지 저장 오류: {e}")
            return False

    async def get_conversation_history(
        self,
        user_id: str,
        limit: int = 10,
        offset: int = 0
    ) -> list:
        """대화 히스토리 조회 - ai_conversations 테이블에서 JSON 파싱"""
        if not self.supabase:
            # Mock 모드
            if not hasattr(self, '_mock_conversations'):
                return []

            user_messages = [
                msg for msg in self._mock_conversations
                if msg["user_id"] == user_id
            ]
            # offset부터 limit개 가져오기
            return user_messages[offset:offset + limit]

        try:
            # ai_conversations 테이블에서 conversation_history JSON 가져오기
            response = self.supabase.table("ai_conversations") \
                .select("conversation_history") \
                .eq("kakao_user_id", user_id) \
                .execute()

            if not response.data or len(response.data) == 0:
                return []

            history = response.data[0].get("conversation_history", [])

            # offset과 limit 적용
            return history[offset:offset + limit]

        except Exception as e:
            print(f"대화 히스토리 조회 오류: {e}")
            return []

    async def count_messages(self, user_id: str) -> int:
        """사용자의 전체 메시지 개수 - ai_conversations JSON 길이"""
        if not self.supabase:
            # Mock 모드
            if not hasattr(self, '_mock_conversations'):
                return 0
            return len([
                msg for msg in self._mock_conversations
                if msg["user_id"] == user_id
            ])

        try:
            response = self.supabase.table("ai_conversations") \
                .select("conversation_history") \
                .eq("kakao_user_id", user_id) \
                .execute()

            if not response.data or len(response.data) == 0:
                return 0

            history = response.data[0].get("conversation_history", [])
            return len(history)

        except Exception as e:
            print(f"메시지 개수 조회 오류: {e}")
            return 0

    async def delete_conversations(self, user_id: str) -> bool:
        """사용자의 모든 대화 삭제 - ai_conversations 테이블"""
        if not self.supabase:
            # Mock 모드
            if hasattr(self, '_mock_conversations'):
                self._mock_conversations = [
                    msg for msg in self._mock_conversations
                    if msg["user_id"] != user_id
                ]
            return True

        try:
            # conversation_history를 빈 배열로 업데이트
            self.supabase.table("ai_conversations") \
                .update({"conversation_history": []}) \
                .eq("kakao_user_id", user_id) \
                .execute()
            return True
        except Exception as e:
            print(f"대화 삭제 오류: {e}")
            return False

    # ============================================
    # 요약 관리 메서드 (conversation_states.temp_data에 저장)
    # ============================================

    async def get_conversation_summary(self, user_id: str) -> Optional[Dict[str, Any]]:
        """대화 요약 조회 - conversation_states.temp_data에서"""
        if not self.supabase:
            # Mock 모드
            if not hasattr(self, '_mock_summaries'):
                self._mock_summaries = {}
            return self._mock_summaries.get(user_id)

        try:
            response = self.supabase.table("conversation_states") \
                .select("temp_data") \
                .eq("kakao_user_id", user_id) \
                .execute()

            if not response.data or len(response.data) == 0:
                return None

            temp_data = response.data[0].get("temp_data", {})
            summary_data = temp_data.get("conversation_summary")

            return summary_data if summary_data else None

        except Exception as e:
            if "PGRST116" in str(e):  # 데이터 없음
                return None
            print(f"요약 조회 오류: {e}")
            return None

    async def save_conversation_summary(
        self,
        user_id: str,
        summary: str,
        summarized_until: int
    ) -> bool:
        """대화 요약 저장 - conversation_states.temp_data에"""
        if not self.supabase:
            # Mock 모드
            if not hasattr(self, '_mock_summaries'):
                self._mock_summaries = {}
            self._mock_summaries[user_id] = {
                "summary": summary,
                "summarized_until": summarized_until,
                "updated_at": datetime.now().isoformat()
            }
            return True

        try:
            # 기존 temp_data 가져오기
            response = self.supabase.table("conversation_states") \
                .select("temp_data") \
                .eq("kakao_user_id", user_id) \
                .execute()

            temp_data = {}
            if response.data and len(response.data) > 0:
                temp_data = response.data[0].get("temp_data", {})

            # 요약 데이터 추가
            temp_data["conversation_summary"] = {
                "summary": summary,
                "summarized_until": summarized_until,
                "updated_at": datetime.now().isoformat()
            }

            # 저장 (upsert)
            self.supabase.table("conversation_states") \
                .upsert({
                    "kakao_user_id": user_id,
                    "current_step": "ai_conversation",  # 기본값
                    "temp_data": temp_data,
                    "updated_at": datetime.now().isoformat()
                }) \
                .execute()

            return True
        except Exception as e:
            print(f"요약 저장 오류: {e}")
            return False

    async def delete_conversation_summary(self, user_id: str) -> bool:
        """대화 요약 삭제 - conversation_states.temp_data에서"""
        if not self.supabase:
            # Mock 모드
            if hasattr(self, '_mock_summaries') and user_id in self._mock_summaries:
                del self._mock_summaries[user_id]
            return True

        try:
            # temp_data에서 conversation_summary만 제거
            response = self.supabase.table("conversation_states") \
                .select("temp_data") \
                .eq("kakao_user_id", user_id) \
                .execute()

            if response.data and len(response.data) > 0:
                temp_data = response.data[0].get("temp_data", {})
                if "conversation_summary" in temp_data:
                    del temp_data["conversation_summary"]

                    self.supabase.table("conversation_states") \
                        .update({"temp_data": temp_data}) \
                        .eq("kakao_user_id", user_id) \
                        .execute()

            return True
        except Exception as e:
            print(f"요약 삭제 오류: {e}")
            return False