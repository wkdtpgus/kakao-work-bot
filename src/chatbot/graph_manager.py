"""
그래프 관리 모듈 - 유저별 워크플로우 관리
"""

from typing import Dict, Optional, Tuple, Any
import logging
from datetime import datetime
from langgraph.graph.state import CompiledStateGraph

from .workflow import build_workflow_graph
from ..utils.models import get_chat_llm, get_onboarding_llm
from ..utils.utils import simple_text_response, error_response
from .state import OnboardingResponse, OverallState, UserContext, UserMetadata, OnboardingStage
from ..database.user_repository import get_user_with_context
from langchain_google_vertexai import ChatVertexAI
import os

logger = logging.getLogger(__name__)


class GraphManager:
    """유저별 그래프 인스턴스 및 요청 내 캐시 관리"""

    def __init__(self, database):
        self.db = database
        self.user_graphs: Dict[str, CompiledStateGraph] = {}
        self.graph_types: Dict[str, CompiledStateGraph] = {}

    async def init_all_graphs(self):
        """모든 그래프 타입 초기화"""
        try:
            # 온보딩용 LLM (structured output, 캐시됨)
            onboarding_llm = get_onboarding_llm().with_structured_output(OnboardingResponse)

            # 서비스용 LLM (일반 채팅, 캐시됨)
            service_llm = get_chat_llm()

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
            # 베이스 그래프를 복사하여 유저별 그래프 생성
            base_graph = self.graph_types.get(graph_type)
            if not base_graph:
                raise ValueError(f"지원하지 않는 그래프 타입: {graph_type}")

            # 새로운 그래프 컴파일 (카카오톡은 stateless이므로 checkpointer 불필요)
            if graph_type == "main":
                # 온보딩용 LLM (캐시됨)
                onboarding_llm = get_onboarding_llm().with_structured_output(OnboardingResponse)

                # 서비스용 LLM (캐시됨)
                service_llm = get_chat_llm()

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

    async def load_request_cache(
        self,
        user_id: str
    ) -> Tuple[UserContext, Optional[Dict[str, Any]], list]:
        """요청 초기화 시 필요한 캐시 데이터 로드

        한 요청 내에서 router → service_router → daily_agent로 전달되는 캐시:
        - user_context: 사용자 메타데이터 + 온보딩 상태
        - conv_state: conversation_states 테이블 데이터
        - today_turns: 오늘 대화 히스토리 (최근 3턴, 요약 시에만 전체 조회)

        Args:
            user_id: 카카오 사용자 ID

        Returns:
            (user_context, conv_state, today_turns)
        """
        # 사용자 정보 + UserContext 로드
        user, user_context = await get_user_with_context(self.db, user_id)

        # conversation_state 조회
        conv_state = await self.db.get_conversation_state(user_id)

        # 오늘 대화 히스토리 조회 (최근 3턴만, 요약 생성 시 전체 재조회)
        today = datetime.now().date().isoformat()
        today_turns = await self.db.get_conversation_history_by_date_v2(user_id, today, limit=3)

        logger.info(
            f"[GraphManager] 캐시 로드 완료 - "
            f"onboarding={user_context.onboarding_stage}, "
            f"today_turns={len(today_turns)}턴"
        )

        return user_context, conv_state, today_turns


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

            # ✅ 요청 캐시 데이터 로드 (DB 쿼리 1회로 모든 필요 데이터 확보)
            user_context, conv_state, today_turns = await self.graph_manager.load_request_cache(user_id)

            # 초기 상태 구성 (캐시 데이터 포함)
            initial_state = OverallState(
                user_id=user_id,
                message=message,
                user_context=user_context,  # ✅ 미리 로드된 컨텍스트
                user_intent=None,   # service_router에서 결정
                ai_response="",
                conversation_history=[],
                conversation_summary="",
                action_hint=action_hint,  # 카카오톡 버튼 힌트
                cached_conv_state=conv_state,  # ✅ 캐시된 대화 상태
                cached_today_turns=today_turns  # ✅ 캐시된 오늘 대화 (최근 3턴)
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