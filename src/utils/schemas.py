"""AI Service Layer Schemas

AI 로직(LLM 호출)의 Input/Output을 명확히 정의하여
데이터 레이어(Repository)와 비즈니스 로직(Service)을 분리합니다.
"""
from pydantic import BaseModel, Field
from typing import Optional


# ============================================
# 공통 스키마
# ============================================

class UserMetadataSchema(BaseModel):
    """사용자 메타데이터 (AI 프롬프트용)"""
    name: str = "사용자"
    job_title: str = "직무 정보 없음"
    project_name: Optional[str] = "프로젝트 정보 없음"
    career_goal: str = "목표 정보 없음"
    total_years: Optional[str] = None
    job_years: Optional[str] = None
    recent_work: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "name": "장세현",
                "job_title": "AI 응용개발자",
                "project_name": "3분커리어",
                "career_goal": "AI 기술 전문가"
            }
        }


# ============================================
# 데일리 요약 Input/Output
# ============================================

class DailySummaryInput(BaseModel):
    """데일리 요약 생성 입력 데이터

    Repository 계층에서 준비하여 AI Service로 전달
    - DB 접근 완료된 상태
    - 포맷팅 완료된 데이터
    """
    user_metadata: UserMetadataSchema = Field(
        description="사용자 메타데이터 (이름, 직무, 프로젝트, 목표 등)"
    )
    conversation_context: str = Field(
        description="포맷팅된 대화 텍스트 (오늘의 모든 대화)"
    )
    attendance_count: int = Field(
        description="현재 출석 카운트 (참조용)"
    )
    daily_record_count: int = Field(
        description="현재 일일 기록 카운트 (참조용)"
    )
    user_correction: Optional[str] = Field(
        default=None,
        description="사용자의 수정 요청 (edit_summary 시 사용)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "user_metadata": {
                    "name": "장세현",
                    "job_title": "AI 응용개발자",
                    "project_name": "3분커리어",
                    "career_goal": "AI 기술 전문가"
                },
                "conversation_context": "사용자: 오늘은 챗봇 개발했어요\n봇: 어떤 부분을 개발하셨나요?\n사용자: 프롬프트 최적화를 진행했습니다\n봇: 좋은 진전이네요!",
                "attendance_count": 7,
                "daily_record_count": 5
            }
        }


class DailySummaryOutput(BaseModel):
    """데일리 요약 생성 출력 데이터

    AI Service에서 LLM 호출 후 반환
    """
    summary_text: str = Field(
        description="LLM이 생성한 데일리 요약 텍스트"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "summary_text": "### 🗂 오늘의 커리어 메모\n\n**3분커리어 챗봇 개발 - 프롬프트 최적화**\n\n- 챗봇 응답 품질 향상을 위한 프롬프트 엔지니어링 진행..."
            }
        }


# ============================================
# 주간 피드백 Input/Output
# ============================================

class WeeklyFeedbackInput(BaseModel):
    """주간 피드백 생성 입력 데이터

    Repository 계층에서 준비하여 AI Service로 전달
    - DB 접근 완료된 상태
    - 7일치 데일리 요약 또는 최근 대화 포맷팅 완료
    """
    user_metadata: UserMetadataSchema = Field(
        description="사용자 메타데이터 (이름, 직무, 목표 등)"
    )
    formatted_context: str = Field(
        description="포맷팅된 데일리 요약 또는 최근 대화 (7일치)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "user_metadata": {
                    "name": "장세현",
                    "job_title": "AI 응용개발자",
                    "career_goal": "AI 기술 전문가"
                },
                "formatted_context": "**2025-10-13**\n오늘은 챗봇 개발...\n\n**2025-10-14**\n프롬프트 최적화...\n\n**2025-10-15**\n레이턴시 개선..."
            }
        }


class WeeklyFeedbackOutput(BaseModel):
    """주간 피드백 생성 출력 데이터

    AI Service에서 LLM 호출 후 반환
    """
    feedback_text: str = Field(
        description="LLM이 생성한 주간 피드백 텍스트"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "feedback_text": "장세현님, 이번 주도 AI 응용개발자로서 매우 의미 있는 성과를 이루셨네요!\n\n1. 이번 주 하이라이트..."
            }
        }
