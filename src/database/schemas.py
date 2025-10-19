"""Database Pydantic Schemas"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime, date


# ============================================
# 1. users 테이블 스키마
# ============================================

class UserSchema(BaseModel):
    """users 테이블 스키마"""
    id: Optional[int] = None
    kakao_user_id: str

    # 온보딩 필드 (9개)
    name: Optional[str] = None
    job_title: Optional[str] = None
    total_years: Optional[str] = None
    job_years: Optional[str] = None
    career_goal: Optional[str] = None
    project_name: Optional[str] = None
    recent_work: Optional[str] = None
    job_meaning: Optional[str] = None
    important_thing: Optional[str] = None

    # 온보딩 완료 여부
    onboarding_completed: bool = False

    # 카운터
    attendance_count: int = 0
    daily_record_count: int = 0
    last_record_date: Optional[date] = None

    # 타임스탬프
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ============================================
# 2. conversation_states 테이블 스키마
# ============================================

class ConversationStateSchema(BaseModel):
    """conversation_states 테이블 스키마"""
    id: Optional[str] = None  # UUID
    kakao_user_id: str
    current_step: Optional[str] = None
    temp_data: Dict[str, Any] = Field(default_factory=dict)
    updated_at: Optional[str] = None


# ============================================
# 3. V2 스키마 - 정규화된 대화 히스토리 테이블
# ============================================

class UserMessageSchema(BaseModel):
    """user_answer_messages 테이블 스키마 (V2)"""
    id: Optional[int] = None
    uuid: Optional[str] = None  # UUID
    kakao_user_id: str
    content: str  # 메시지 내용
    created_at: Optional[str] = None


class AIMessageSchema(BaseModel):
    """ai_answer_messages 테이블 스키마 (V2)"""
    id: Optional[int] = None
    uuid: Optional[str] = None  # UUID
    kakao_user_id: str
    content: str  # 메시지 내용
    is_summary: bool = False  # 요약 여부
    summary_type: Optional[str] = None  # 'daily', 'weekly', None
    created_at: Optional[str] = None


class MessageTurnSchema(BaseModel):
    """message_history 테이블 스키마 (V2) - 대화 턴 (user-ai 쌍)"""
    id: Optional[int] = None
    uuid: Optional[str] = None  # UUID
    kakao_user_id: str
    user_answer_key: str  # user_answer_messages의 UUID
    ai_answer_key: str  # ai_answer_messages의 UUID
    session_date: str  # YYYY-MM-DD
    turn_index: Optional[int] = None  # 날짜 내 턴 순서
    created_at: Optional[str] = None
