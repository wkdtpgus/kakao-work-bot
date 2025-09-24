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
            response = self.supabase.table("users").upsert(user_data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"사용자 생성/업데이트 오류: {e}")
            raise e

    async def get_conversation_state(self, user_id: str) -> Optional[Dict[str, Any]]:
        """대화 상태 조회"""
        if not self.supabase:
            return self._mock_states.get(user_id)

        try:
            response = self.supabase.table("conversation_states").select("*").eq("kakao_user_id", user_id).single().execute()
            return response.data if response.data else None
        except Exception as e:
            if "PGRST116" in str(e):  # 데이터 없음
                return None
            print(f"대화 상태 조회 오류: {e}")
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
            response = self.supabase.table("conversation_states").upsert(state_data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"대화 상태 생성/업데이트 오류: {e}")
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