# 메모리 관리 가이드

## 📋 개요

카카오톡 챗봇의 메모리는 **숏텀-롱텀 전략**을 사용합니다.

### 메모리 구조

| 메모리 타입 | 저장 위치 | 삭제 여부 | 용도 |
|------------|----------|----------|------|
| **롱텀 - 사용자 정보** | `users` 테이블 | ❌ 영구 | 이름, 경력, 목표 등 구조화 데이터 |
| **롱텀 - 대화 전문** | `conversations` 테이블 | ❌ 영구 | 모든 대화 기록 (분석/리뷰용) |
| **숏텀 - 요약** | `conversation_summaries` 테이블 | ✅ 삭제 가능 | LLM 컨텍스트 (토큰 절약) |
| **숏텀 - 최근 N개** | `conversations` 조회 | - | LLM 컨텍스트 (정확도) |

---

## 🚀 설치 및 설정

### 1. Supabase 테이블 생성

Supabase 대시보드의 SQL Editor에서 실행:

```bash
cat supabase_migration.sql
```

위 파일의 SQL을 Supabase에서 실행하면 다음 테이블이 생성됩니다:
- `conversations` - 대화 전문 저장
- `conversation_summaries` - 대화 요약 저장

### 2. 환경 변수 확인

`.env` 파일에 다음이 설정되어 있는지 확인:

```env
SUPABASE_URL=your_supabase_url
SUPABASE_ANON_KEY=your_anon_key
OPENAI_API_KEY=your_openai_key
```

---

## 💡 사용 방법

### 기본 사용 (nodes.py에서)

```python
from src.chatbot.memory_manager import MemoryManager

memory_manager = MemoryManager()

# 1️⃣ 대화 컨텍스트 가져오기 (숏텀 메모리)
context = await memory_manager.get_contextualized_history(user_id, db)

# 결과:
# {
#   "summary": "지난 대화 요약 (20개 이상일 때)",
#   "recent_turns": [최근 10개 메시지],
#   "total_count": 전체 메시지 개수,
#   "summarized_count": 요약된 메시지 개수
# }

# 2️⃣ LLM 프롬프트 구성
prompt = f"""
이전 대화 요약:
{context['summary']}

최근 대화:
{format_turns(context['recent_turns'])}

현재 질문: {user_message}
"""

# 3️⃣ 응답 생성 후 저장
response = await llm.ainvoke(prompt)
await memory_manager.add_messages(user_id, user_message, response, db)
```

---

## 🔄 동작 흐름

### 턴 1~20: 요약 없음

```python
# 20개 이하면 전부 원문으로 반환
context = {
    "summary": "",
    "recent_turns": [턴1~20],
    "total_count": 20,
    "summarized_count": 0
}
```

### 턴 40: 첫 요약 발생

```python
# 자동으로 요약 생성 (gpt-4o-mini 사용)
context = {
    "summary": "턴1~30 요약: 사용자는 경력 고민 중...",
    "recent_turns": [턴31~40],  # 최근 10개만
    "total_count": 40,
    "summarized_count": 30
}
```

### 턴 60: 요약 업데이트

```python
# 기존 요약 + 새 메시지(턴31~50) 통합
context = {
    "summary": "턴1~50 요약: 경력 고민 → 이력서 작성 조언...",
    "recent_turns": [턴51~60],
    "total_count": 60,
    "summarized_count": 50
}
```

---

## 🛠️ 고급 사용법

### 메모리 초기화

```python
# 요약만 삭제 (대화 전문은 유지)
await memory_manager.clear_short_term(user_id, db)

# 모든 메모리 삭제 (주의: 복구 불가)
await memory_manager.clear_all_memory(user_id, db)
```

### 전체 대화 히스토리 조회 (분석용)

```python
# 모든 대화 가져오기 (요약 없이)
total = await db.count_messages(user_id)
all_messages = await db.get_conversation_history(user_id, limit=total)
```

### 사용자 컨텍스트 조회 (롱텀 + 숏텀)

```python
context = await memory_manager.get_user_context(user_id, db)

# 결과:
# {
#   "user_data": {이름, 경력 등},
#   "conversation_summary": "요약",
#   "recent_conversations": [최근 10개],
#   "total_message_count": 40
# }
```

---

## ⚙️ 설정 변경

`memory_manager.py`에서 임계값 조정:

```python
class MemoryManager:
    def __init__(self):
        self.recent_message_threshold = 10  # 최근 N개 (기본 10)
        self.summary_trigger = 20  # 요약 시작 (기본 20)
```

**예시:**
- `recent_message_threshold = 5`: 최근 5개만 원문
- `summary_trigger = 30`: 30개부터 요약 생성

---

## 🐛 트러블슈팅

### 요약이 생성 안 됨

1. OpenAI API 키 확인: `.env`의 `OPENAI_API_KEY`
2. 메시지 개수 확인: 20개 이상이어야 요약 생성
3. 로그 확인: `🔄 요약 업데이트 필요` 메시지 출력 여부

### Mock 모드에서 데이터 안 보임

Mock 모드는 메모리 기반이므로 서버 재시작 시 데이터 소실됩니다.
Supabase 연결을 확인하세요:

```python
await db.test_connection()
```

### 대화가 너무 길어서 느림

`summary_trigger` 값을 낮춰서 더 빨리 요약하세요:

```python
self.summary_trigger = 15  # 15개부터 요약
```

---

## 📊 성능 최적화

### 토큰 절약

- **요약 없이**: 40턴 = 약 8,000 토큰
- **요약 사용**: 요약(500토큰) + 최근 10턴(2,000토큰) = **2,500 토큰**
- **절약률**: 약 **70% 감소**

### DB 쿼리 최적화

인덱스가 자동 생성되므로 사용자별 조회가 빠릅니다:
- `idx_conversations_user_created` - 사용자별 최근 대화
- `idx_summaries_user` - 사용자별 요약

---

## 🔒 보안

### Row Level Security (RLS)

선택적으로 활성화 가능 (`supabase_migration.sql` 참고):

```sql
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
```

### 데이터 삭제 정책

- `conversations`: 영구 보관 (삭제 안 함)
- `conversation_summaries`: 필요 시 삭제 가능

---

## 📝 참고

- 대화 전문은 **영구 보관**됩니다
- 요약은 **자동 생성**됩니다 (LLM 호출)
- 최근 N개는 **항상 원문**으로 유지됩니다
