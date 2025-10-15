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


# 모델 설정만 저장
CHAT_MODEL_CONFIG = {
    "model_name": CHAT_MODEL_NAME,
    "temperature": CHAT_TEMPERATURE,
    "max_output_tokens": CHAT_MAX_TOKENS,
}

ONBOARDING_MODEL_CONFIG = {
    "model_name": ONBOARDING_MODEL_NAME,
    "temperature": ONBOARDING_TEMPERATURE,
    "max_output_tokens": ONBOARDING_MAX_TOKENS,
}

SUMMARY_MODEL_CONFIG = {
    "model_name": SUMMARY_MODEL_NAME,
    "temperature": SUMMARY_TEMPERATURE,
    "max_output_tokens": SUMMARY_MAX_TOKENS,
}