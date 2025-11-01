from langchain_google_vertexai import ChatVertexAI
from ..config.config import (
    CHAT_MODEL_NAME,
    CHAT_TEMPERATURE,
    CHAT_MAX_TOKENS,
    CHAT_TIMEOUT,
    ONBOARDING_MODEL_NAME,
    ONBOARDING_TEMPERATURE,
    ONBOARDING_MAX_TOKENS,
    ONBOARDING_TIMEOUT,
    SUMMARY_MODEL_NAME,
    SUMMARY_TEMPERATURE,
    SUMMARY_MAX_TOKENS,
    SUMMARY_TIMEOUT,
)


# Vertex AI 모델 설정 (credentials는 환경변수에서 자동 로드)
CHAT_MODEL_CONFIG = {
    "model_name": CHAT_MODEL_NAME,
    "temperature": CHAT_TEMPERATURE,
    "max_output_tokens": CHAT_MAX_TOKENS,
    # Vertex AI는 timeout 대신 request_timeout 사용 (선택적)
}

ONBOARDING_MODEL_CONFIG = {
    "model_name": ONBOARDING_MODEL_NAME,
    "temperature": ONBOARDING_TEMPERATURE,
    "max_output_tokens": ONBOARDING_MAX_TOKENS,
    # Vertex AI는 timeout 대신 request_timeout 사용 (선택적)
}

SUMMARY_MODEL_CONFIG = {
    "model_name": SUMMARY_MODEL_NAME,
    "temperature": SUMMARY_TEMPERATURE,
    "max_output_tokens": SUMMARY_MAX_TOKENS,
    # Vertex AI는 timeout 대신 request_timeout 사용 (선택적)
}


# =============================================================================
# LLM 인스턴스 캐싱 (싱글톤 패턴)
# =============================================================================

_cached_chat_llm = None
_cached_onboarding_llm = None
_cached_summary_llm = None


def get_chat_llm() -> ChatVertexAI:
    """일반 채팅용 LLM 인스턴스 반환 (캐시됨)"""
    global _cached_chat_llm
    if _cached_chat_llm is None:
        _cached_chat_llm = ChatVertexAI(**CHAT_MODEL_CONFIG)
    return _cached_chat_llm


def get_onboarding_llm() -> ChatVertexAI:
    """온보딩용 LLM 인스턴스 반환 (캐시됨)"""
    global _cached_onboarding_llm
    if _cached_onboarding_llm is None:
        _cached_onboarding_llm = ChatVertexAI(**ONBOARDING_MODEL_CONFIG)
    return _cached_onboarding_llm


def get_summary_llm() -> ChatVertexAI:
    """요약용 LLM 인스턴스 반환 (캐시됨)"""
    global _cached_summary_llm
    if _cached_summary_llm is None:
        _cached_summary_llm = ChatVertexAI(**SUMMARY_MODEL_CONFIG)
    return _cached_summary_llm