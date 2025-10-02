"""
QA Agent용 도구들
"""

from typing import Optional
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
import os
from ..utils.models import CHAT_MODEL_CONFIG


# =============================================================================
# Tool Input Schemas
# =============================================================================

class QualityQuestionInput(BaseModel):
    """양질의 질문 생성 툴 입력"""
    user_context: str = Field(description="사용자의 직무, 목표, 최근 업무 등 컨텍스트")
    topic: Optional[str] = Field(default=None, description="질문 주제 (예: 커리어, 프로젝트, 성과)")


class WeeklyFeedbackInput(BaseModel):
    """주간 피드백 생성 툴 입력"""
    weekly_records: str = Field(description="주간 기록 내용 (JSON 또는 텍스트)")
    user_metadata: str = Field(description="사용자 메타데이터 (이름, 직무, 목표 등)")


class TemplateInput(BaseModel):
    """템플릿 생성 툴 입력"""
    template_type: str = Field(description="템플릿 종류 (예: 일일기록, 회고, 이력서)")
    user_context: str = Field(description="사용자 컨텍스트")


# =============================================================================
# Tools
# =============================================================================

class QualityQuestionTool(BaseTool):
    """양질의 질문 생성 도구

    사용자의 일일 기록을 돕기 위해 맥락에 맞는 깊이 있는 질문을 생성합니다.
    """

    name: str = "quality_question_generator"
    description: str = """사용자의 직무와 목표에 맞는 양질의 질문을 생성합니다.
    이 도구는 사용자가 자신의 업무를 더 깊이 성찰할 수 있도록 돕습니다.
    입력: user_context (사용자 정보), topic (선택 주제)
    출력: 3-5개의 성찰 질문 리스트"""
    args_schema: type[BaseModel] = QualityQuestionInput

    def _run(self, user_context: str, topic: Optional[str] = None) -> str:
        """질문 생성 실행"""
        llm = ChatOpenAI(**CHAT_MODEL_CONFIG, api_key=os.getenv("OPENAI_API_KEY"))

        prompt = f"""사용자 컨텍스트:
{user_context}

주제: {topic or '일일 업무 기록'}

위 사용자의 직무와 목표에 맞는 깊이 있는 성찰 질문 3-5개를 생성해주세요.
질문은 사용자가 자신의 업무 경험을 더 깊이 탐구하고, 배움과 성장을 발견할 수 있도록 도와야 합니다.

출력 형식:
1. [질문]
2. [질문]
..."""

        response = llm.invoke([
            SystemMessage(content="당신은 커리어 코칭 전문가입니다. 사용자의 성장을 돕는 통찰력 있는 질문을 생성합니다."),
            HumanMessage(content=prompt)
        ])

        return response.content

    async def _arun(self, user_context: str, topic: Optional[str] = None) -> str:
        """비동기 실행"""
        llm = ChatOpenAI(**CHAT_MODEL_CONFIG, api_key=os.getenv("OPENAI_API_KEY"))

        prompt = f"""사용자 컨텍스트:
{user_context}

주제: {topic or '일일 업무 기록'}

위 사용자의 직무와 목표에 맞는 깊이 있는 성찰 질문 3-5개를 생성해주세요.
질문은 사용자가 자신의 업무 경험을 더 깊이 탐구하고, 배움과 성장을 발견할 수 있도록 도와야 합니다.

출력 형식:
1. [질문]
2. [질문]
..."""

        response = await llm.ainvoke([
            SystemMessage(content="당신은 커리어 코칭 전문가입니다. 사용자의 성장을 돕는 통찰력 있는 질문을 생성합니다."),
            HumanMessage(content=prompt)
        ])

        return response.content


class WeeklyFeedbackTool(BaseTool):
    """주간 피드백 생성 도구

    일주일 간의 일일 기록을 분석하여 인사이트와 피드백을 제공합니다.
    """

    name: str = "weekly_feedback_generator"
    description: str = """주간 기록을 분석하여 피드백을 생성합니다.
    패턴 인식, 성과 하이라이트, 개선 제안 등을 포함합니다.
    입력: weekly_records (주간 기록), user_metadata (사용자 정보)
    출력: 구조화된 주간 피드백 리포트"""
    args_schema: type[BaseModel] = WeeklyFeedbackInput

    def _run(self, weekly_records: str, user_metadata: str) -> str:
        """피드백 생성 실행"""
        llm = ChatOpenAI(**CHAT_MODEL_CONFIG, api_key=os.getenv("OPENAI_API_KEY"))

        prompt = f"""사용자 정보:
{user_metadata}

주간 기록:
{weekly_records}

위 주간 기록을 분석하여 다음 내용을 포함한 피드백을 생성해주세요:
1. 이번 주 하이라이트 (주요 성과 3가지)
2. 발견된 패턴 (업무 패턴, 성장 포인트)
3. 다음 주 제안 (개선 방향, 실행 가능한 조언)

출력은 친근하고 격려하는 톤으로 작성해주세요."""

        response = llm.invoke([
            SystemMessage(content="당신은 경력 개발 코치입니다. 사용자의 주간 기록을 분석하여 통찰력 있는 피드백을 제공합니다."),
            HumanMessage(content=prompt)
        ])

        return response.content

    async def _arun(self, weekly_records: str, user_metadata: str) -> str:
        """비동기 실행"""
        llm = ChatOpenAI(**CHAT_MODEL_CONFIG, api_key=os.getenv("OPENAI_API_KEY"))

        prompt = f"""사용자 정보:
{user_metadata}

주간 기록:
{weekly_records}

위 주간 기록을 분석하여 다음 내용을 포함한 피드백을 생성해주세요:
1. 이번 주 하이라이트 (주요 성과 3가지)
2. 발견된 패턴 (업무 패턴, 성장 포인트)
3. 다음 주 제안 (개선 방향, 실행 가능한 조언)

출력은 친근하고 격려하는 톤으로 작성해주세요."""

        response = await llm.ainvoke([
            SystemMessage(content="당신은 경력 개발 코치입니다. 사용자의 주간 기록을 분석하여 통찰력 있는 피드백을 제공합니다."),
            HumanMessage(content=prompt)
        ])

        return response.content


class TemplateTool(BaseTool):
    """템플릿 생성 도구

    일일 기록, 회고, 이력서 등 다양한 템플릿을 사용자에 맞게 생성합니다.
    """

    name: str = "template_generator"
    description: str = """사용자 맞춤형 템플릿을 생성합니다.
    일일 기록, 회고, 이력서 등의 템플릿을 제공합니다.
    입력: template_type (템플릿 종류), user_context (사용자 정보)
    출력: 맞춤형 템플릿 텍스트"""
    args_schema: type[BaseModel] = TemplateInput

    def _run(self, template_type: str, user_context: str) -> str:
        """템플릿 생성 실행"""
        # TODO: LLM을 사용한 실제 템플릿 생성 로직

        templates = {
            "일일기록": """
📝 일일 기록 템플릿

날짜: [YYYY-MM-DD]

오늘의 주요 업무:
•

어려웠던 점 / 도전:
•

배운 점 / 인사이트:
•

내일 계획:
•
""",
            "회고": """
🔍 회고 템플릿

기간: [시작일 ~ 종료일]

잘한 점 (Keep):
•

개선할 점 (Problem):
•

시도해볼 점 (Try):
•
""",
            "이력서": """
📄 경력 기술서 템플릿

[프로젝트명]
• 기간:
• 역할:
• 사용 기술:
• 주요 성과:
• 배운 점:
"""
        }

        return templates.get(template_type, "해당 템플릿을 찾을 수 없습니다.").strip()

    async def _arun(self, template_type: str, user_context: str) -> str:
        """비동기 실행"""
        return self._run(template_type, user_context)


# =============================================================================
# Tool List
# =============================================================================

def get_qa_tools():
    """QA Agent에서 사용할 도구 리스트 반환"""
    return [
        QualityQuestionTool(),
        WeeklyFeedbackTool(),
        TemplateTool()
    ]
