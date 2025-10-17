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
# 3. ai_conversations 테이블 스키마
# ============================================

class ConversationMessageSchema(BaseModel):
    """ai_conversations JSON 메시지 스키마"""
    role: str  # "user" or "assistant"
    content: str
    created_at: str


class AIConversationSchema(BaseModel):
    """ai_conversations 테이블 스키마"""
    id: Optional[str] = None  # UUID
    kakao_user_id: str
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)
    updated_at: Optional[str] = None


# ============================================
# 4. daily_records 테이블 스키마
# ============================================

class DailyRecordSchema(BaseModel):
    """daily_records 테이블 스키마"""
    id: Optional[int] = None
    user_id: int  # users.id (BIGINT)
    work_content: str
    record_date: str  # YYYY-MM-DD
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ============================================
# 5. weekly_summaries 테이블 스키마
# ============================================

class WeeklySummarySchema(BaseModel):
    """weekly_summaries 테이블 스키마"""
    id: Optional[int] = None
    kakao_user_id: str
    sequence_number: int
    start_daily_count: int
    end_daily_count: int
    summary_content: str
    start_date: Optional[str] = None  # YYYY-MM-DD
    end_date: Optional[str] = None  # YYYY-MM-DD
    created_at: Optional[str] = None
