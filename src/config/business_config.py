"""애플리케이션 전역 상수 정의

이 파일에 정의된 상수를 변경하면 전체 시스템에 반영됩니다.
"""

# =============================================================================
# 일일 기록 관련 상수
# =============================================================================

# 일일 대화 턴 수 기준 (attendance_count 증가 조건)
DAILY_TURNS_THRESHOLD = 4
"""하루 완료로 인정되는 최소 대화 턴 수
- 이 값에 도달하면 attendance_count가 1 증가
- 변경 시 영향: database.py, user_repository.py, utils.py
"""

# 요약 제안 기준
SUMMARY_SUGGESTION_THRESHOLD = 4
"""일일 요약 제안을 시작하는 대화 횟수
- 세션 내 conversation_count가 이 값 이상이면 요약 제안
- 변경 시 영향: record_handler.py, record_processor.py
"""

# 주간 요약 생성을 위한 최소 평일 작성 일수
WEEKLY_SUMMARY_MIN_WEEKDAY_COUNT = 2
"""주간 요약 생성에 필요한 최소 평일(월~금) 작성 일수
- 평일 작성이 이 개수 미만이면 주간 요약 제안 안 함
- 주말(토요일 오후 6시)에만 제안
- 변경 시 영향: record_handler.py, summary_repository.py
"""

# =============================================================================
# 대화 히스토리 관련 상수
# =============================================================================

# 컨텍스트로 제공할 최근 대화 턴 수
MAX_CONTEXT_TURNS = 3
"""LLM 프롬프트에 포함할 최근 대화 턴 수
- 변경 시 영향: utils.py (format_conversation_history)
"""

# 온보딩 대화 히스토리 최대 보관 개수
MAX_ONBOARDING_HISTORY = 20
"""온보딩 단계에서 보관할 최대 대화 개수
- 변경 시 영향: utils.py (save_onboarding_conversation)
"""
