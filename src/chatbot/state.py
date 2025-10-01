"""
LangGraph용 대화 상태 관리
"""

from typing import List, Dict, Any, Optional, TypedDict
from dataclasses import dataclass
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field
from typing import Optional


class OnboardingResponse(BaseModel):
    """온보딩 응답 모델"""
    response: str
    name: Optional[str] = None
    job_title: Optional[str] = None
    total_years: Optional[str] = None
    job_years: Optional[str] = None
    career_goal: Optional[str] = None
    project_name: Optional[str] = None
    recent_work: Optional[str] = None
    job_meaning: Optional[str] = None
    important_thing: Optional[str] = None


class OnboardingState(TypedDict):
    """전체 플로우 상태"""
    user_id: str
    message: str
    current_state: Dict[str, Any]
    ai_response: str
    updated_variables: Dict[str, Any]
    conversation_history: list
    conversation_summary: str  # 대화 요약 (숏텀 메모리)
    next_step: str  # continue_onboarding, daily_reflection, weekly_wrapup


@dataclass
class ConversationState:
    """대화 상태를 관리하는 데이터클래스"""

    # 기본 식별자
    user_id: str

    # 메시지 관련
    messages: List[BaseMessage]
    conversation_history: List[Dict[str, str]]

    # 대화 상태
    current_step: str
    intent: str
    ai_response: str

    # 사용자 데이터
    user_data: Optional[Dict[str, Any]] = None
    temp_data: Optional[Dict[str, Any]] = None

    # 컨텍스트 정보
    context: Optional[Dict[str, Any]] = None
    conversation_topic: Optional[str] = None

    # 메타 정보
    is_first_message: bool = False
    requires_immediate_response: bool = False