"""
LangGraph 멀티 스텝 워크플로우
"""

from functools import partial
from langgraph.graph import StateGraph
from .state import OverallState
from . import nodes


def build_workflow_graph(db, memory_manager, onboarding_llm, service_llm) -> StateGraph:
    """멀티 스텝 워크플로우 그래프 구성

    Flow:
    START → router_node
      ├─ onboarding_agent_node → END
      └─ service_router_node
          ├─ daily_agent_node
          │   ├─ (일반) → END
          │   └─ (7일차) → weekly_agent_node → END
          └─ weekly_agent_node → END
    """

    # StateGraph 생성
    workflow = StateGraph(OverallState)

    # 노드 추가 (Agent Executor 제거, 단순 LLM 호출만 사용)
    workflow.add_node("router_node",
                     partial(nodes.router_node, db=db))

    workflow.add_node("service_router_node",
                     partial(nodes.service_router_node, llm=service_llm, db=db, memory_manager=memory_manager))

    workflow.add_node("onboarding_agent_node",
                     partial(nodes.onboarding_agent_node, db=db, memory_manager=memory_manager, llm=onboarding_llm))

    workflow.add_node("daily_agent_node",
                     partial(nodes.daily_agent_node, db=db, memory_manager=memory_manager))

    workflow.add_node("weekly_agent_node",
                     partial(nodes.weekly_agent_node, db=db, memory_manager=memory_manager))

    # 시작점 설정
    workflow.set_entry_point("router_node")

    # 엣지는 Command의 goto로 자동 처리
    # router_node → onboarding_agent_node OR service_router_node
    # service_router_node → daily_agent_node OR weekly_agent_node
    # 각 agent 노드 → END

    return workflow.compile()


