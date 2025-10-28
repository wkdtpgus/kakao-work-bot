"""
LangGraph용 대화 상태 관리
"""

from typing import List, Dict, Any, Optional, TypedDict
from dataclasses import dataclass
from datetime import date
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field
from enum import Enum


class OnboardingStage(str, Enum):
    """온보딩 단계"""
    NOT_STARTED = "not_started"
    COLLECTING_BASIC = "collecting_basic"  # 이름, 직무, 연차
    COLLECTING_GOAL = "collecting_goal"    # 커리어 목표
    COLLECTING_PROJECT = "collecting_project"  # 프로젝트 정보
    COLLECTING_WORK = "collecting_work"    # 최근 업무
    COLLECTING_VALUES = "collecting_values"  # 직무 의미, 중요한 것
    COMPLETED = "completed"


class OnboardingResponse(BaseModel):
    """온보딩 응답 모델 (Structured Output용)"""
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

    # 🆕 LLM이 판단한 필드 상태
    field_status: Optional[Dict[str, str]] = Field(default_factory=dict)
    # {"job_title": "partial"} - 모호하거나 불충분한 답변인 경우만 표시

    # 🆕 명확화 요청 감지
    is_clarification_request: bool = False
    # True면 시도 횟수를 증가시키지 않음


class UserMetadata(BaseModel):
    """사용자 메타데이터"""
    name: Optional[str] = None
    job_title: Optional[str] = None
    total_years: Optional[str] = None
    job_years: Optional[str] = None
    career_goal: Optional[str] = None
    project_name: Optional[str] = None
    recent_work: Optional[str] = None
    job_meaning: Optional[str] = None
    important_thing: Optional[str] = None

    # 루프 방지: 시도 횟수 및 상태 추적
    field_attempts: Dict[str, int] = Field(default_factory=dict)
    # {"name": 1, "job_title": 2, "career_goal": 3, ...}

    field_status: Dict[str, str] = Field(default_factory=dict)
    # {"job_title": "partial", "career_goal": "skipped", "name": "filled"}


class UserContext(BaseModel):
    """사용자 컨텍스트 (라우터에서 사용)"""
    user_id: str
    onboarding_stage: OnboardingStage = OnboardingStage.NOT_STARTED
    metadata: Optional[UserMetadata] = None
    attendance_count: int = 0  # 출석(일일기록) 카운트
    daily_record_count: int = 0  # 일일 대화 카운트 (5회 달성 시 attendance_count 증가)
    last_record_date: Optional[date] = None
    daily_session_data: Optional[Dict[str, Any]] = Field(default_factory=dict)  # 일일 세션 데이터 (대화 횟수 추적)


class OnboardingIntent(str, Enum):
    """온보딩 중 사용자 의도 분류"""
    ANSWER = "answer"           # 질문에 답변함 (모든 답변 포함)
    CLARIFICATION = "clarification"  # 질문의 의미를 모르겠음
    INVALID = "invalid"         # 무관한 내용


class ExtractionResponse(BaseModel):
    """LLM의 정보 추출 결과 (응답 생성 X)"""
    intent: OnboardingIntent
    extracted_value: Optional[str] = None  # 추출된 값
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)  # 신뢰도
    clarification_needed: bool = False  # 추가 확인 필요 여부
    detected_field: Optional[str] = None  # 감지된 필드명 (순서 외 정보 제공 시)


class UserIntent(str, Enum):
    """사용자 의도"""
    DAILY_RECORD = "daily_record"  # 일일 기록
    WEEKLY_FEEDBACK = "weekly_feedback"  # 주간 피드백
    GENERAL_CHAT = "general_chat"  # 일반 대화


class OverallState(TypedDict):
    """전체 워크플로우 상태"""
    user_id: str
    message: str
    user_context: UserContext
    user_intent: Optional[str]  # UserIntent 값
    ai_response: str
    conversation_history: List[BaseMessage]
    conversation_summary: str
    action_hint: Optional[str]  # 카카오톡 버튼 힌트 ("onboarding", "daily_record", "service_feedback")

    # DB 쿼리 캐시 (한 요청 내에서 재사용)
    cached_conv_state: Optional[Dict[str, Any]]  # ConversationStateSchema
    cached_today_turns: Optional[List[Dict[str, Any]]]  # 오늘 대화 목록 (요약 시 전체, 일반 대화 시 최근 3턴)


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