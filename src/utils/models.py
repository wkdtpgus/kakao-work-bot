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