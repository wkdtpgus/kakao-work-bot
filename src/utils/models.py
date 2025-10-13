from langchain_openai import ChatOpenAI
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


# 모델 설정만 저장 (API 키는 사용처에서 주입)
CHAT_MODEL_CONFIG = {
    "model": CHAT_MODEL_NAME,
    "temperature": CHAT_TEMPERATURE,
    "max_tokens": CHAT_MAX_TOKENS,
    "timeout": CHAT_TIMEOUT,
}

ONBOARDING_MODEL_CONFIG = {
    "model": ONBOARDING_MODEL_NAME,
    "temperature": ONBOARDING_TEMPERATURE,
    "max_tokens": ONBOARDING_MAX_TOKENS,
    "timeout": ONBOARDING_TIMEOUT,
}

SUMMARY_MODEL_CONFIG = {
    "model": SUMMARY_MODEL_NAME,
    "temperature": SUMMARY_TEMPERATURE,
    "max_tokens": SUMMARY_MAX_TOKENS,
    "timeout": SUMMARY_TIMEOUT,
}