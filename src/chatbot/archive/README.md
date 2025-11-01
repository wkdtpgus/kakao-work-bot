# Archive

이 폴더는 마이그레이션 완료 후 더 이상 사용하지 않는 코드를 보관합니다.

## nodes.py

**아카이브 날짜**: 2025-11-01

**이유**: LangGraph 노드 기반 아키텍처에서 AgentExecutor + Tool 기반 아키텍처로 완전 마이그레이션

**마이그레이션 위치**:
- `router_node` → `agent_node.py` (onboarding_stage 체크)
- `service_router_node` → `agent_node.py` (classify_user_intent 호출)
- `onboarding_agent_node` → `tools/onboarding_tool.py`
- `daily_agent_node` → `tools/daily_conversation_tool.py`, `tools/daily_summary_tool.py`, `tools/edit_summary_tool.py`
- `weekly_agent_node` → `tools/weekly_summary_tool.py`

**주요 변경사항**:
- 복잡한 노드 기반 라우팅 → LLM Tool Calling으로 자동 툴 선택
- 각 기능별 독립적인 Tool 클래스로 모듈화
- 모든 로직 보존 (특수 의도 하드코딩 응답, is_valid_turn 플래그, conversation_count 제어 등)
- Repository 패턴 활용으로 DB 로직 중복 제거

**참고**: 이 파일은 롤백이나 참고용으로 보관됩니다.
