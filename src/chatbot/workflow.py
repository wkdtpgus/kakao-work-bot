"""
LangGraph 멀티 스텝 워크플로우
"""

from typing import Dict, Any
from functools import partial
import os
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import create_react_agent
from .state import OverallState, OnboardingResponse
from ..utils.utils import simple_text_response, error_response
from .memory_manager import MemoryManager
from . import nodes
from .tools import get_qa_tools


def build_workflow_graph(db, memory_manager, onboarding_llm, service_llm) -> StateGraph:
    """멀티 스텝 워크플로우 그래프 구성

    Flow:
    START → router_node
      ├─ onboarding_agent_node → END
      └─ service_router_node
          ├─ daily_agent_node → END
          └─ weekly_agent_node → END
    """

    # StateGraph 생성
    workflow = StateGraph(OverallState)

    # AgentExecutor 생성 (일일/주간 agent용)
    tools = get_qa_tools()
    agent_executor = create_react_agent(service_llm, tools)

    # 노드 추가
    workflow.add_node("router_node",
                     partial(nodes.router_node, db=db))

    workflow.add_node("service_router_node",
                     partial(nodes.service_router_node, llm=service_llm))

    workflow.add_node("onboarding_agent_node",
                     partial(nodes.onboarding_agent_node, db=db, memory_manager=memory_manager, llm=onboarding_llm))

    workflow.add_node("daily_agent_node",
                     partial(nodes.daily_agent_node, db=db, memory_manager=memory_manager, agent_executor=agent_executor))

    workflow.add_node("weekly_agent_node",
                     partial(nodes.weekly_agent_node, db=db, memory_manager=memory_manager, agent_executor=agent_executor))

    # 시작점 설정
    workflow.set_entry_point("router_node")

    # 엣지는 Command의 goto로 자동 처리
    # router_node → onboarding_agent_node OR service_router_node
    # service_router_node → daily_agent_node OR weekly_agent_node
    # 각 agent 노드 → END

    return workflow.compile()


