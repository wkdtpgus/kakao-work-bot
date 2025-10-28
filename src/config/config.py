# 대화 모델 설정 (Google Vertex AI)
# CHAT_MODEL_NAME = "gpt-4.1-mini"  # OpenAI (backup)
CHAT_MODEL_NAME = "gemini-2.5-flash-lite"
CHAT_TEMPERATURE = 0.0
CHAT_MAX_TOKENS = 500
CHAT_TIMEOUT = 10.0

# 온보딩 모델 설정 (Google Vertex AI)
# ONBOARDING_MODEL_NAME = "gpt-4.1-mini"  # OpenAI (backup)
ONBOARDING_MODEL_NAME = "gemini-2.5-flash-lite"
ONBOARDING_TEMPERATURE = 0.0
ONBOARDING_MAX_TOKENS = 500
ONBOARDING_TIMEOUT = 10.0

# 요약 모델 설정 (Google Vertex AI)
# SUMMARY_MODEL_NAME = "gpt-4.1-mini"  # OpenAI (backup)
SUMMARY_MODEL_NAME = "gemini-2.5-flash-lite"
SUMMARY_TEMPERATURE = 0.0
SUMMARY_MAX_TOKENS = 400  # 한글 900자 이내 목표 (여유 확보, 강제 종료 방지)
SUMMARY_TIMEOUT = 10.0
