"""AI Service Layer Schemas

AI 로직(LLM 호출)의 Input/Output을 명확히 정의하여
데이터 레이어(Repository)와 비즈니스 로직(Service)을 분리합니다.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from dataclasses import dataclass


# ============================================
# 대화 히스토리 스키마
# ============================================

@dataclass
class ConversationTurn:
    """대화 턴 스키마 (DB: conversation_turns_v2)

    ⚠️ IMPORTANT: DB에서 로드 시 turn_index DESC 정렬 (최신이 [0])

    Attributes:
        turn_index: 턴 순서 (1부터 시작)
        user_message: 사용자 메시지
        ai_message: AI 응답
        created_at: 생성 시각 (ISO 8601 형식)
        is_summary: 요약 턴 여부
        summary_type: 요약 타입 ("daily", "weekly", None)
    """
    turn_index: int
    user_message: str
    ai_message: str
    created_at: str
    is_summary: bool = False
    summary_type: Optional[Literal["daily", "weekly"]] = None

    @classmethod
    def from_dict(cls, data: dict) -> "ConversationTurn":
        """DB 결과(dict)를 ConversationTurn으로 변환

        Args:
            data: DB 쿼리 결과 dict

        Returns:
            ConversationTurn 인스턴스
        """
        return cls(
            turn_index=data["turn_index"],
            user_message=data["user_message"],
            ai_message=data["ai_message"],
            created_at=data["created_at"],
            is_summary=data.get("is_summary", False),
            summary_type=data.get("summary_type")
        )


class ConversationHistory:
    """대화 히스토리 헬퍼 클래스

    대화 턴 목록을 관리하고 편리한 메서드를 제공합니다.

    ⚠️ IMPORTANT: turns는 turn_index DESC 정렬 (최신이 [0])

    Examples:
        >>> turns = [ConversationTurn.from_dict(t) for t in db_results]
        >>> history = ConversationHistory(turns)
        >>> last_message = history.get_last_ai_message()
        >>> recent_3 = history.get_recent(3)
    """

    def __init__(self, turns: List[ConversationTurn]):
        """
        Args:
            turns: 내림차순 정렬된 대화 턴 목록 (최신이 [0])
        """
        self.turns = turns

    def get_last_ai_message(self) -> Optional[str]:
        """가장 최근 AI 응답 추출

        Returns:
            가장 최근 AI 응답 또는 None (대화 없을 시)
        """
        if not self.turns:
            return None
        return self.turns[0].ai_message

    def get_recent(self, n: int) -> List[ConversationTurn]:
        """최근 N개 턴 추출

        Args:
            n: 추출할 턴 개수

        Returns:
            최근 N개 턴 목록 (내림차순 정렬 유지)
        """
        return self.turns[:n]

    def to_llm_format(self, reverse: bool = True) -> str:
        """LLM용 대화 히스토리 포맷팅

        Args:
            reverse: True면 시간순(오래된 게 먼저), False면 역순

        Returns:
            포맷팅된 대화 문자열

        Example:
            >>> history.to_llm_format()
            "User: 안녕\nBot: 안녕하세요!\nUser: 오늘 뭐했어?\nBot: 말씀해주세요!"
        """
        turns_to_format = list(reversed(self.turns)) if reverse else self.turns
        return "\n".join([
            f"User: {t.user_message}\nBot: {t.ai_message}"
            for t in turns_to_format
        ])

    def __len__(self) -> int:
        """대화 턴 개수 반환"""
        return len(self.turns)

    def __bool__(self) -> bool:
        """대화 존재 여부 (빈 리스트면 False)"""
        return bool(self.turns)


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
