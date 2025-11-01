"""
LangGraph 워크플로우 - AgentExecutor 기반 통합 아키텍처
"""

from functools import partial
from langgraph.graph import StateGraph
from .state import OverallState
from .agent_node import unified_agent_node


def build_workflow_graph(db, onboarding_llm, service_llm) -> StateGraph:
    """통합 에이전트 워크플로우 그래프 구성

    New Architecture:
    START → unified_agent_node → END

    unified_agent_node가 LLM Tool Calling으로 적절한 툴을 선택:
    - OnboardingTool: 온보딩 처리
    - DailyConversationTool: 일일 대화
    - DailySummaryTool: 일일 요약 생성
    - EditSummaryTool: 요약 수정
    - WeeklySummaryTool: 주간 피드백 생성
    """

    # StateGraph 생성
    workflow = StateGraph(OverallState)

    # 통합 에이전트 노드 추가
    workflow.add_node(
        "unified_agent_node",
        partial(
            unified_agent_node,
            db=db,
            onboarding_llm=onboarding_llm,
            service_llm=service_llm
        )
    )

    # 시작점 설정
    workflow.set_entry_point("unified_agent_node")

    # unified_agent_node → END (Command의 goto로 처리)

    return workflow.compile()


