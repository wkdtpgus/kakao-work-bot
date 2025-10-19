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

    async def get_user(self, user_id: str) -> Optional["UserSchema"]:
        """사용자 정보 조회

        Returns:
            Optional[UserSchema]: UserSchema 객체 (없으면 None)
        """
        from .schemas import UserSchema

        if not self.supabase:
            mock_data = self._mock_users.get(user_id)
            return UserSchema(**mock_data) if mock_data else None

        try:
            response = self.supabase.table("users").select("*").eq("kakao_user_id", user_id).single().execute()
            if not response.data:
                return None

            # dict → UserSchema 변환 (Pydantic이 타입 변환 자동 처리)
            return UserSchema(**response.data)
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
            # 기존 사용자 확인
            existing_user = await self.get_user(user_id)

            if existing_user:
                # ✅ 기존 사용자 업데이트 (update 사용)
                print(f"🔄 [DB] 기존 사용자 업데이트: {user_id}, 필드: {list(user_data.keys())}")
                response = self.supabase.table("users").update(
                    user_data
                ).eq("kakao_user_id", user_id).execute()
                return response.data[0] if response.data else None
            else:
                # ✅ 신규 사용자 생성 (insert 사용)
                print(f"✨ [DB] 신규 사용자 생성: {user_id}")
                user_data["kakao_user_id"] = user_id
                response = self.supabase.table("users").insert(user_data).execute()
                return response.data[0] if response.data else None

        except Exception as e:
            print(f"❌ [DB] 사용자 생성/업데이트 오류: {e}")
            import traceback
            traceback.print_exc()
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

    # ============================================
    # 일일기록 카운트 관리
    # ============================================

    async def increment_daily_record_count(self, user_id: str) -> int:
        """오늘의 대화 턴 수 증가 (날짜 변경 시 자동 리셋)

        Returns:
            int: 증가된 daily_record_count
        """
        try:
            today = datetime.now().date()
            user = await self.get_user(user_id)

            if not user:
                print(f"❌ [DB] 사용자 정보 없음: {user_id}")
                return 0

            last_record_date = user.last_record_date
            current_daily_count = user.daily_record_count

            if last_record_date == today:
                # 오늘 대화 → 카운트 증가
                new_daily_count = current_daily_count + 1
            else:
                # 날짜 변경 → 리셋 후 1로 시작
                new_daily_count = 1
                print(f"📅 [DB] 날짜 변경 감지 → daily_record_count 리셋: {user_id}")

            # daily_record_count와 last_record_date 함께 업데이트
            await self.create_or_update_user(user_id, {
                "daily_record_count": new_daily_count,
                "last_record_date": today.isoformat()
            })
            print(f"✅ [DB] daily_record_count 업데이트: {user_id} → {new_daily_count}회")
            return new_daily_count

        except Exception as e:
            print(f"❌ [DB] daily_record_count 증가 실패: {e}")
            return 0

    async def increment_attendance_count(self, user_id: str, daily_record_count: int) -> int:
        """출석(일일기록) 카운트 증가 및 현재 카운트 반환 (5회 턴 조건)

        Args:
            user_id: 사용자 ID
            daily_record_count: 오늘의 대화 턴 수

        Returns:
            int: 업데이트된 attendance_count

        로직:
            - daily_record_count가 정확히 5일 때만 호출됨 (nodes.py에서 제어)
            - 호출되면 무조건 +1 증가 (중복 체크는 nodes.py의 "== 5" 조건이 자동으로 방지)
        """
        try:
            user = await self.get_user(user_id)

            if not user:
                print(f"❌ [DB] 사용자 정보 없음: {user_id}")
                return 0

            current_count = user.attendance_count

            # 안전장치: 5회 미만이면 증가 안 함
            if daily_record_count < 5:
                print(f"⏳ [DB] 대화 턴 부족 (현재 {daily_record_count}회, 5회 필요): {user_id}")
                return current_count

            # 5회 달성 → 카운트 증가
            new_count = current_count + 1
            await self.create_or_update_user(user_id, {
                "attendance_count": new_count
            })
            print(f"✅ [DB] attendance_count 증가 (5회 턴 달성): {user_id} → {new_count}일차")
            return new_count

        except Exception as e:
            print(f"❌ [DB] attendance_count 증가 실패: {e}")
            return 0

    # =============================================================================
    # 주간 요약 관리 (weekly_summaries 테이블) - DEPRECATED
    # =============================================================================
    # ⚠️ DEPRECATED: V2 스키마에서는 ai_answer_messages 테이블 사용
    # - 저장: save_conversation_turn(is_summary=True, summary_type='weekly')
    # - 조회: summary_messages_view 사용 (summary_type='weekly' 필터)

    async def save_weekly_summary(
        self,
        user_id: str,
        sequence_number: int,
        start_daily_count: int,
        end_daily_count: int,
        summary_content: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> bool:
        """⚠️ DEPRECATED: V2 스키마에서는 save_conversation_turn(is_summary=True, summary_type='weekly') 사용

        주간 요약 저장
        """
        if not self.supabase:
            print("⚠️ [DB] Supabase 미연결 - 주간요약 저장 스킵")
            return False

        try:
            data = {
                "kakao_user_id": user_id,
                "sequence_number": sequence_number,
                "start_daily_count": start_daily_count,
                "end_daily_count": end_daily_count,
                "summary_content": summary_content,
                "start_date": start_date,
                "end_date": end_date,
                "created_at": datetime.now().isoformat()
            }

            self.supabase.table("weekly_summaries").upsert(
                data,
                on_conflict="kakao_user_id,sequence_number"
            ).execute()

            print(f"✅ [DB] 주간요약 저장 완료: {user_id} - {sequence_number}번째 ({start_daily_count}-{end_daily_count}일차)")
            return True

        except Exception as e:
            print(f"❌ [DB] 주간요약 저장 실패: {e}")
            return False

    async def get_weekly_summaries(self, user_id: str, limit: int = 10) -> list:
        """⚠️ DEPRECATED: V2 스키마에서는 summary_messages_view 사용 (summary_type='weekly' 필터)

        유저의 주간요약 목록 조회 (최신순)
        """
        if not self.supabase:
            return []

        try:
            response = self.supabase.table("weekly_summaries")\
                .select("*")\
                .eq("kakao_user_id", user_id)\
                .order("sequence_number", desc=True)\
                .limit(limit)\
                .execute()

            return response.data if response.data else []

        except Exception as e:
            print(f"❌ [DB] 주간요약 목록 조회 실패: {e}")
            return []

    async def get_weekly_summary_by_sequence(self, user_id: str, sequence_number: int) -> Optional[Dict]:
        """⚠️ DEPRECATED: V2 스키마에서는 summary_messages_view 사용 (summary_type='weekly' 필터)

        특정 시퀀스의 주간요약 조회
        """
        if not self.supabase:
            return None

        try:
            response = self.supabase.table("weekly_summaries")\
                .select("*")\
                .eq("kakao_user_id", user_id)\
                .eq("sequence_number", sequence_number)\
                .single()\
                .execute()

            return response.data if response.data else None

        except Exception as e:
            print(f"❌ [DB] 주간요약 조회 실패: {e}")
            return None

    async def get_latest_weekly_summary(self, user_id: str) -> Optional[Dict]:
        """⚠️ DEPRECATED: V2 스키마에서는 summary_messages_view 사용 (summary_type='weekly' 필터)

        최신 주간요약 조회
        """
        if not self.supabase:
            return None

        try:
            response = self.supabase.table("weekly_summaries")\
                .select("*")\
                .eq("kakao_user_id", user_id)\
                .order("sequence_number", desc=True)\
                .limit(1)\
                .execute()

            return response.data[0] if response.data else None

        except Exception as e:
            print(f"❌ [DB] 최신 주간요약 조회 실패: {e}")
            return None


    # =============================================================================
    # V2 스키마 - 정규화된 대화 히스토리 관리
    # =============================================================================

    async def save_conversation_turn(
        self,
        user_id: str,
        user_message: str,
        ai_message: str,
        is_summary: bool = False,
        summary_type: str = None
    ) -> Optional[Dict[str, Any]]:
        """대화 턴 저장 (V2 스키마)

        user_answer_messages, ai_answer_messages, message_history 테이블에 저장

        Args:
            user_id: 카카오 사용자 ID
            user_message: 사용자 메시지
            ai_message: AI 응답
            is_summary: 요약 메시지 여부 (기본 False)
            summary_type: 요약 타입 ('daily', 'weekly', None)

        Returns:
            dict: {
                "history_uuid": "...",
                "user_uuid": "...",
                "ai_uuid": "...",
                "turn_index": 1,
                "session_date": "2025-10-19"
            }
        """
        if not self.supabase:
            print("⚠️ [DB] Supabase 미연결 - 대화 턴 저장 스킵")
            return None

        try:
            from datetime import date
            session_date = date.today().isoformat()

            # 1. 오늘 날짜의 turn_index 계산
            turn_count_response = self.supabase.table("message_history") \
                .select("turn_index", count="exact") \
                .eq("kakao_user_id", user_id) \
                .eq("session_date", session_date) \
                .execute()

            turn_index = (turn_count_response.count or 0) + 1

            # 2. user_answer_messages 저장
            user_response = self.supabase.table("user_answer_messages").insert({
                "kakao_user_id": user_id,
                "content": user_message
            }).execute()

            if not user_response.data:
                print(f"❌ [DB V2] user_answer_messages 저장 실패")
                return None

            user_uuid = user_response.data[0]["uuid"]

            # 3. ai_answer_messages 저장
            ai_response = self.supabase.table("ai_answer_messages").insert({
                "kakao_user_id": user_id,
                "content": ai_message,
                "is_summary": is_summary,
                "summary_type": summary_type  # 🆕 추가
            }).execute()

            if not ai_response.data:
                print(f"❌ [DB V2] ai_answer_messages 저장 실패")
                return None

            ai_uuid = ai_response.data[0]["uuid"]

            # 4. message_history에 턴 저장
            history_response = self.supabase.table("message_history").insert({
                "kakao_user_id": user_id,
                "user_answer_key": user_uuid,
                "ai_answer_key": ai_uuid,
                "session_date": session_date,
                "turn_index": turn_index
            }).execute()

            if not history_response.data:
                print(f"❌ [DB V2] message_history 저장 실패")
                return None

            history_uuid = history_response.data[0]["uuid"]

            print(f"✅ [DB V2] 대화 턴 저장 완료: {user_id} - 턴 #{turn_index}")

            return {
                "history_uuid": history_uuid,
                "user_uuid": user_uuid,
                "ai_uuid": ai_uuid,
                "turn_index": turn_index,
                "session_date": session_date
            }

        except Exception as e:
            print(f"❌ [DB V2] 대화 턴 저장 실패: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def get_recent_turns_v2(
        self,
        user_id: str,
        limit: int = 5
    ) -> list:
        """최근 N개 턴 조회 (V2 스키마 - RPC 함수 사용)

        Args:
            user_id: 카카오 사용자 ID
            limit: 조회할 턴 수 (기본 5개)

        Returns:
            list: [
                {
                    "turn_index": 3,
                    "user_message": "...",
                    "ai_message": "...",
                    "session_date": "2025-10-15",
                    "created_at": "..."
                },
                ...
            ]
        """
        if not self.supabase:
            return []

        try:
            response = self.supabase.rpc(
                "get_recent_turns",
                {
                    "p_kakao_user_id": user_id,
                    "p_limit": limit
                }
            ).execute()

            return response.data if response.data else []

        except Exception as e:
            print(f"❌ [DB V2] 최근 턴 조회 실패: {e}")
            return []

    async def get_shortterm_memory_v2(self, user_id: str) -> list:
        """숏텀 메모리 조회 (V2 스키마 - recent_conversations 뷰 사용)

        Args:
            user_id: 카카오 사용자 ID

        Returns:
            list: [
                {"user": "안녕", "ai": "안녕하세요"},
                {"user": "오늘 뭐했어", "ai": "..."},
                ...
            ]
        """
        if not self.supabase:
            return []

        try:
            response = self.supabase.table("recent_conversations") \
                .select("recent_turns") \
                .eq("kakao_user_id", user_id) \
                .execute()

            if response.data and len(response.data) > 0:
                return response.data[0].get("recent_turns", [])
            return []

        except Exception as e:
            print(f"❌ [DB V2] 숏텀 메모리 조회 실패: {e}")
            return []

    async def get_daily_summaries_v2(self, user_id: str, limit: int = 7) -> list:
        """데일리 요약 조회 (V2 스키마 - RPC 함수 사용)

        하루에 여러 데일리 요약을 생성한 경우, 각 날짜별 최신 요약만 반환합니다.
        이를 통해 주간 요약 생성 시 정확히 7일치 데이터를 가져올 수 있습니다.

        Args:
            user_id: 카카오 사용자 ID
            limit: 조회할 고유 날짜 수 (기본 7개)

        Returns:
            list: [
                {
                    "summary_content": "오늘의 요약...",
                    "session_date": "2025-10-19",
                    "created_at": "...",
                    "summary_type": "daily"
                },
                ...
            ]
        """
        if not self.supabase:
            return []

        try:
            # RPC 함수 호출 (DISTINCT ON session_date로 각 날짜별 최신 요약만 선택)
            response = self.supabase.rpc(
                'get_recent_daily_summaries_by_unique_dates',
                {
                    'p_kakao_user_id': user_id,
                    'p_limit': limit
                }
            ).execute()

            return response.data if response.data else []

        except Exception as e:
            print(f"❌ [DB V2] 데일리 요약 조회 실패: {e}")
            return []

    async def get_conversation_history_by_date_v2(
        self,
        user_id: str,
        date: str,
        limit: int = 50
    ) -> list:
        """특정 날짜의 대화 턴 조회 (V2 스키마 - RPC 함수 사용)

        Args:
            user_id: 카카오 사용자 ID
            date: 조회할 날짜 (YYYY-MM-DD)
            limit: 최대 조회 개수

        Returns:
            list: [
                {
                    "turn_index": 1,
                    "user_message": "...",
                    "ai_message": "...",
                    "created_at": "..."
                },
                ...
            ]
        """
        if not self.supabase:
            return []

        try:
            response = self.supabase.rpc(
                "get_turns_by_date",
                {
                    "p_kakao_user_id": user_id,
                    "p_session_date": date
                }
            ).execute()

            return response.data if response.data else []

        except Exception as e:
            print(f"❌ [DB V2] 날짜별 대화 조회 실패: {e}")
            return []

    async def get_conversation_history_for_llm_v2(
        self,
        user_id: str,
        limit: int = 10
    ) -> list:
        """LLM API 호출용 대화 히스토리 변환 (V2 스키마)

        Args:
            user_id: 카카오 사용자 ID
            limit: 조회할 턴 수 (기본 10개)

        Returns:
            list: [
                {"role": "user", "content": "안녕"},
                {"role": "assistant", "content": "안녕하세요"},
                ...
            ]
        """
        try:
            # 5개 이하면 숏텀 메모리 사용 (빠름)
            if limit <= 5:
                recent_turns = await self.get_shortterm_memory_v2(user_id)

                # JSONB 형식 → LLM 형식 변환 (오래된 순으로)
                messages = []
                for turn in reversed(recent_turns):
                    messages.append({"role": "user", "content": turn.get("user", "")})
                    messages.append({"role": "assistant", "content": turn.get("ai", "")})

                return messages

            # 더 많은 히스토리 필요 시 DB 조회
            else:
                turns = await self.get_recent_turns_v2(user_id, limit)

                messages = []
                # reversed로 오래된 순으로 변환
                for turn in reversed(turns):
                    messages.append({"role": "user", "content": turn.get("user_message", "")})
                    messages.append({"role": "assistant", "content": turn.get("ai_message", "")})

                return messages

        except Exception as e:
            print(f"❌ [DB V2] LLM용 히스토리 변환 실패: {e}")
            return []