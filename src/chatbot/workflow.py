"""
LangGraph 온보딩 워크플로우
"""

from typing import Dict, Any
from functools import partial
import os
from langgraph.graph import StateGraph, END
from .state import OnboardingState, OnboardingResponse
from .utils import ResponseFormatter, PromptLoader, get_openai_model
from .memory_manager import MemoryManager
from . import nodes


def route_next_step(state: OnboardingState) -> str:
    """다음 단계 라우팅"""
    return state.get("next_step", "continue_onboarding")


def build_workflow_graph(db, memory_manager, llm, prompt_loader) -> StateGraph:
    """워크플로우 그래프 구성"""

    # StateGraph 생성
    workflow = StateGraph(OnboardingState)

    # 기본 노드들 추가 (partial로 의존성 주입)
    workflow.add_node("load_user_state",
                     partial(nodes.load_user_state, db=db, memory_manager=memory_manager))
    workflow.add_node("check_next_step",
                     partial(nodes.check_next_step, db=db))

    # 온보딩 노드들
    workflow.add_node("generate_ai_response",
                     partial(nodes.generate_ai_response, llm=llm, prompt_loader=prompt_loader))
    workflow.add_node("update_user_info",
                     partial(nodes.update_user_info, db=db, memory_manager=memory_manager))

    # 일일 회고 노드들
    workflow.add_node("start_daily_reflection", nodes.start_daily_reflection)
    workflow.add_node("collect_daily_tasks", nodes.collect_daily_tasks)

    # 주간 랩업 노드들
    workflow.add_node("start_weekly_wrapup", nodes.start_weekly_wrapup)
    workflow.add_node("generate_weekly_insights", nodes.generate_weekly_insights)
    workflow.add_node("save_weekly_summary", nodes.save_weekly_summary)

    # 공통 저장 노드
    workflow.add_node("save_conversation",
                     partial(nodes.save_conversation, memory_manager=memory_manager, db=db))

    # 엣지 정의
    workflow.set_entry_point("load_user_state")

    # 기본 플로우
    workflow.add_edge("load_user_state", "check_next_step")

    # 조건부 라우팅
    workflow.add_conditional_edges(
        "check_next_step",
        route_next_step,
        {
            "continue_onboarding": "generate_ai_response",
            "daily_reflection": "start_daily_reflection",
            "weekly_wrapup": "start_weekly_wrapup"
        }
    )

    # 온보딩 플로우
    workflow.add_edge("generate_ai_response", "update_user_info")
    workflow.add_edge("update_user_info", "save_conversation")

    # 일일 회고 플로우
    workflow.add_edge("start_daily_reflection", "save_conversation")
    # TODO: 나중에 실제 대화 플로우 구현시 더 복잡한 연결

    # 주간 랩업 플로우
    workflow.add_edge("start_weekly_wrapup", "generate_weekly_insights")
    workflow.add_edge("generate_weekly_insights", "save_weekly_summary")
    workflow.add_edge("save_weekly_summary", "save_conversation")

    # 최종 종료
    workflow.add_edge("save_conversation", END)

    return workflow.compile()


# 글로벌 메모리 매니저 (사용자별 캐시 유지용)
_global_memory_manager = None

async def handle_onboarding_conversation(user_id: str, message: str, db) -> Dict[str, Any]:
    """온보딩 대화 처리 메인 함수"""
    try:
        print(f"🤖 온보딩 대화 시작: {user_id}")
        print(f"📨 받은 메시지: {message}")

        # 글로벌 메모리 매니저 사용 (캐시 유지)
        global _global_memory_manager
        if _global_memory_manager is None:
            _global_memory_manager = MemoryManager()

        memory_manager = _global_memory_manager
        prompt_loader = PromptLoader()
        formatter = ResponseFormatter()
        llm = get_openai_model().with_structured_output(OnboardingResponse)

        # 워크플로우 그래프 생성
        graph = build_workflow_graph(db, memory_manager, llm, prompt_loader)

        # 초기 상태 구성
        initial_state = OnboardingState(
            user_id=user_id,
            message=message,
            current_state={},
            ai_response="",
            updated_variables={},
            conversation_history=[],
            next_step=""
        )

        # 워크플로우 실행
        final_state = await graph.ainvoke(initial_state)

        # 최종 응답 반환
        ai_response = final_state["ai_response"]
        return formatter.simple_text_response(ai_response)

    except Exception as error:
        print(f"온보딩 대화 처리 오류: {error}")
        import traceback
        traceback.print_exc()
        formatter = ResponseFormatter()
        return formatter.error_response(
            "AI 대화 처리 중 오류가 발생했습니다. 다시 시도해주세요."
        )


