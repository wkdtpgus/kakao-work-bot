"""
그래프 관리 모듈 - 유저별 워크플로우 관리
"""

from typing import Dict, Optional
import logging
from langgraph.graph.state import CompiledStateGraph
from langgraph.checkpoint.memory import MemorySaver

from .workflow import build_workflow_graph
from ..utils.models import CHAT_MODEL_CONFIG, ONBOARDING_MODEL_CONFIG
from ..utils.utils import simple_text_response, error_response
from .state import OnboardingResponse, OverallState, UserContext, UserMetadata, OnboardingStage
from langchain_google_vertexai import ChatVertexAI
import os

logger = logging.getLogger(__name__)


class GraphManager:
    """유저별 그래프 인스턴스 관리"""

    def __init__(self, database):
        self.db = database
        self.user_graphs: Dict[str, CompiledStateGraph] = {}
        self.memory_savers: Dict[str, MemorySaver] = {}
        self.graph_types: Dict[str, CompiledStateGraph] = {}

    async def init_all_graphs(self):
        """모든 그래프 타입 초기화"""
        try:
            # 온보딩용 LLM (structured output)
            chat_model = ChatVertexAI(**ONBOARDING_MODEL_CONFIG)
            onboarding_llm = chat_model.with_structured_output(OnboardingResponse)

            # 서비스용 LLM (일반 채팅)
            service_llm = ChatVertexAI(**CHAT_MODEL_CONFIG)

            main_graph = build_workflow_graph(self.db, onboarding_llm, service_llm)
            self.graph_types["main"] = main_graph

            logger.info("모든 그래프 타입 초기화 완료")

        except Exception as e:
            logger.error(f"그래프 초기화 실패: {e}")
            raise

    def get_or_create_user_graph(self, user_id: str, graph_type: str = "main") -> CompiledStateGraph:
        """유저별 그래프를 가져오거나 생성"""
        user_graph_key = f"{user_id}_{graph_type}"

        if user_graph_key not in self.user_graphs:
            # 유저별 MemorySaver 생성
            memory_saver = MemorySaver()
            self.memory_savers[user_graph_key] = memory_saver

            # 베이스 그래프를 복사하여 유저별 그래프 생성
            base_graph = self.graph_types.get(graph_type)
            if not base_graph:
                raise ValueError(f"지원하지 않는 그래프 타입: {graph_type}")

            # 메모리 세이버와 함께 새로운 그래프 컴파일
            if graph_type == "main":
                # 온보딩용 LLM
                chat_model = ChatVertexAI(**ONBOARDING_MODEL_CONFIG)
                onboarding_llm = chat_model.with_structured_output(OnboardingResponse)

                # 서비스용 LLM
                service_llm = ChatVertexAI(**CHAT_MODEL_CONFIG)

                user_graph = build_workflow_graph(self.db, onboarding_llm, service_llm)
            else:
                user_graph = base_graph

            self.user_graphs[user_graph_key] = user_graph
            logger.info(f"유저 그래프 생성: {user_id} ({graph_type})")

        return self.user_graphs[user_graph_key]

    def get_user_graph(self, user_id: str, graph_type: str = "main") -> CompiledStateGraph:
        """유저 그래프 가져오기 (없으면 생성)"""
        return self.get_or_create_user_graph(user_id, graph_type)

    def reset_user_graph(self, user_id: str, graph_type: str = "onboarding") -> None:
        """유저 그래프 초기화"""
        user_graph_key = f"{user_id}_{graph_type}"

        if user_graph_key in self.user_graphs:
            del self.user_graphs[user_graph_key]
            logger.info(f"유저 그래프 삭제: {user_id} ({graph_type})")

        if user_graph_key in self.memory_savers:
            del self.memory_savers[user_graph_key]
            logger.info(f"유저 메모리 삭제: {user_id} ({graph_type})")

    def reset_all_user_graphs(self, user_id: str) -> None:
        """특정 유저의 모든 그래프 초기화"""
        keys_to_delete = []

        # 삭제할 키들 찾기
        for key in self.user_graphs.keys():
            if key.startswith(f"{user_id}_"):
                keys_to_delete.append(key)

        # 그래프들 삭제
        for key in keys_to_delete:
            if key in self.user_graphs:
                del self.user_graphs[key]
            if key in self.memory_savers:
                del self.memory_savers[key]

        logger.info(f"유저의 모든 그래프 삭제: {user_id}")

    async def determine_graph_type(self, user_id: str, message: str) -> str:
        """메시지와 유저 상태를 기반으로 적절한 그래프 타입 결정"""
        # 통합 구조이므로 항상 main
        return "main"

    def get_available_graph_types(self) -> list:
        """사용 가능한 그래프 타입 목록 반환"""
        return list(self.graph_types.keys())

    def get_user_graph_stats(self) -> Dict[str, int]:
        """유저 그래프 통계 반환"""
        stats = {}
        for graph_type in self.graph_types.keys():
            count = sum(1 for key in self.user_graphs.keys() if key.endswith(f"_{graph_type}"))
            stats[graph_type] = count

        stats["total_users"] = len(set(key.split("_")[0] for key in self.user_graphs.keys()))
        return stats


class ChatBotManager:
    """챗봇 전체 관리 클래스"""

    def __init__(self, database):
        self.db = database
        self.graph_manager = GraphManager(database)

    async def initialize(self):
        """챗봇 매니저 초기화"""
        await self.graph_manager.init_all_graphs()
        logger.info("ChatBotManager 초기화 완료")

    async def get_user_info(self, user_id: str) -> Dict:
        """사용자 정보 조회 (API 레이어 분리)"""
        user = await self.db.get_user(user_id)
        return user if user else {}

    async def handle_conversation(self, user_id: str, message: str, action_hint: str = None) -> Dict:
        """대화 처리 - 워크플로우 진입점"""
        try:
            # ✅ 캐싱된 그래프 가져오기 (없으면 생성)
            graph = self.graph_manager.get_or_create_user_graph(user_id, graph_type="main")

            # 초기 상태 구성
            initial_state = OverallState(
                user_id=user_id,
                message=message,
                user_context=None,  # router에서 로드
                user_intent=None,   # service_router에서 결정
                ai_response="",
                conversation_history=[],
                conversation_summary="",
                action_hint=action_hint  # 카카오톡 버튼 힌트
            )

            # 워크플로우 실행
            final_state = await graph.ainvoke(initial_state)

            # 최종 응답 반환
            ai_response = final_state.get("ai_response", "응답 생성 중 오류가 발생했습니다.")
            return simple_text_response(ai_response)

        except Exception as e:
            logger.error(f"대화 처리 실패: {e}")
            import traceback
            traceback.print_exc()
            return error_response("대화 처리 중 오류가 발생했습니다.")


# 싱글톤 인스턴스는 main.py에서 생성