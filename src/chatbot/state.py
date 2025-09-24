"""
LangGraph용 대화 상태 관리
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from langchain_core.messages import BaseMessage


@dataclass
class ConversationState:
    """대화 상태를 관리하는 데이터클래스"""

    # 기본 식별자
    user_id: str

    # 메시지 관련
    messages: List[BaseMessage]
    conversation_history: List[Dict[str, str]]

    # 대화 상태
    current_step: str
    intent: str
    ai_response: str

    # 사용자 데이터
    user_data: Optional[Dict[str, Any]] = None
    temp_data: Optional[Dict[str, Any]] = None

    # 컨텍스트 정보
    context: Optional[Dict[str, Any]] = None
    conversation_topic: Optional[str] = None

    # 메타 정보
    is_first_message: bool = False
    requires_immediate_response: bool = False