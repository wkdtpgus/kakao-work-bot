"""
그래프 관리 모듈 - 유저별 워크플로우 관리
"""

from typing import Dict, Optional
import logging
from langgraph.graph.state import CompiledStateGraph
from langgraph.checkpoint.memory import MemorySaver

from .workflow import handle_onboarding_conversation, build_workflow_graph
from .utils import ResponseFormatter, PromptLoader, get_openai_model
from .memory_manager import MemoryManager
from .state import OnboardingResponse

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
            # 온보딩 워크플로우 초기화
            memory_manager = MemoryManager()
            prompt_loader = PromptLoader()
            llm = get_openai_model().with_structured_output(OnboardingResponse)

            onboarding_graph = build_workflow_graph(self.db, memory_manager, llm, prompt_loader)
            self.graph_types["onboarding"] = onboarding_graph

            logger.info("모든 그래프 타입 초기화 완료")

        except Exception as e:
            logger.error(f"그래프 초기화 실패: {e}")
            raise

    def get_or_create_user_graph(self, user_id: str, graph_type: str = "onboarding") -> CompiledStateGraph:
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
            if graph_type == "onboarding":
                memory_manager = MemoryManager()
                prompt_loader = PromptLoader()
                llm = get_openai_model().with_structured_output(OnboardingResponse)
                user_graph = build_workflow_graph(self.db, memory_manager, llm, prompt_loader)
                # 메모리 세이버 설정 (필요한 경우)
                # user_graph = user_graph.with_config({"checkpointer": memory_saver})
            else:
                user_graph = base_graph

            self.user_graphs[user_graph_key] = user_graph
            logger.info(f"유저 그래프 생성: {user_id} ({graph_type})")

        return self.user_graphs[user_graph_key]

    def get_user_graph(self, user_id: str, graph_type: str = "onboarding") -> CompiledStateGraph:
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
        try:
            # 사용자 정보 가져오기
            user = await self.db.get_user(user_id)

            # 온보딩 완료 여부 확인
            if not user or not user.get("onboarding_completed"):
                return "onboarding"

            # 키워드 기반 그래프 타입 결정
            if "온보딩" in message or "처음" in message:
                return "onboarding"
            elif "이력서" in message or "resume" in message.lower():
                return "resume"  # 나중에 구현
            elif "면접" in message:
                return "interview"  # 나중에 구현
            else:
                return "general"  # 일반 대화 - 나중에 구현

        except Exception as e:
            logger.error(f"그래프 타입 결정 실패: {e}")
            return "onboarding"  # 기본값

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

    async def handle_conversation(self, user_id: str, message: str) -> Dict:
        """대화 처리 - 적절한 그래프 선택하여 실행"""
        try:
            # 적절한 그래프 타입 결정
            graph_type = await self.graph_manager.determine_graph_type(user_id, message)
            logger.info(f"선택된 그래프 타입: {graph_type} (유저: {user_id})")

            # 유저별 그래프 가져오기
            user_graph = self.graph_manager.get_user_graph(user_id, graph_type)

            # 그래프 타입별 처리
            if graph_type == "onboarding":
                # 온보딩 워크플로우 실행
                return await handle_onboarding_conversation(user_id, message, self.db)
            else:
                # 다른 워크플로우들은 나중에 구현
                formatter = ResponseFormatter()
                return formatter.simple_text_response(
                    f"죄송합니다. '{graph_type}' 기능은 아직 개발 중입니다."
                )

        except Exception as e:
            logger.error(f"대화 처리 실패: {e}")
            formatter = ResponseFormatter()
            return formatter.error_response("대화 처리 중 오류가 발생했습니다.")


# 싱글톤 인스턴스는 main.py에서 생성