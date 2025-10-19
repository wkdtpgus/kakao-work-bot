# 🚀 DB 스키마 V2 마이그레이션 가이드

## 📊 새로운 스키마 구조

### 핵심 테이블 3개 + 뷰 3개

**테이블 (물리적 저장)**
```
1. user_answer_messages (유저 메시지)
   ├── uuid (랜덤 키값)
   ├── kakao_user_id
   ├── content (메시지 내용)
   └── created_at

2. ai_answer_messages (AI 응답)
   ├── uuid (랜덤 키값)
   ├── kakao_user_id
   ├── content (메시지 내용)
   ├── is_summary (요약 여부)
   └── created_at

3. message_history (대화 턴 히스토리)
   ├── uuid (랜덤 키값)
   ├── kakao_user_id
   ├── user_answer_key → user_answer_messages.uuid
   ├── ai_answer_key → ai_answer_messages.uuid
   ├── session_date
   ├── turn_index
   └── daily_record_id
```

**뷰 (실시간 조회)**
```
4. recent_conversations (최근 5개 턴 자동 조회)
   ├── kakao_user_id
   └── recent_turns (JSONB 배열)

5. daily_conversation_stats (날짜별 대화 통계)
   ├── kakao_user_id
   ├── session_date
   └── turn_count

6. summary_messages_view (요약 메시지만 조회)
   ├── summary_content
   ├── is_summary = TRUE
   └── user_request
```

---

## 🔧 Python 코드 수정 (database.py)

### 1. 메시지 저장 로직

#### AS-IS (기존)
```python
async def save_message(self, kakao_user_id: str, role: str, content: str):
    """기존 JSONB 배열 방식"""
    response = self.supabase.table("ai_conversations") \
        .select("conversation_history") \
        .eq("kakao_user_id", kakao_user_id) \
        .execute()

    history = response.data[0]["conversation_history"] if response.data else []
    history.append({
        "role": role,
        "content": content,
        "created_at": datetime.now().isoformat()
    })

    self.supabase.table("ai_conversations").upsert({
        "kakao_user_id": kakao_user_id,
        "conversation_history": history
    }).execute()
```

#### TO-BE (V2 스키마)
```python
from datetime import date, datetime
from typing import Tuple, Optional

async def save_conversation_turn(
    self,
    kakao_user_id: str,
    user_message: str,
    ai_message: str
) -> dict:
    """
    대화 턴 저장 (user-ai 쌍)

    Returns:
        dict: {
            "history_uuid": "...",
            "user_uuid": "...",
            "ai_uuid": "...",
            "turn_index": 1
        }
    """
    session_date = str(date.today())

    # 1. 오늘 날짜의 turn_index 계산
    turn_count = self.supabase.table("message_history") \
        .select("turn_index", count="exact") \
        .eq("kakao_user_id", kakao_user_id) \
        .eq("session_date", session_date) \
        .execute()

    turn_index = (turn_count.count or 0) + 1

    # 2. user_answer_messages 저장
    user_response = self.supabase.table("user_answer_messages").insert({
        "kakao_user_id": kakao_user_id,
        "content": user_message
    }).execute()
    user_uuid = user_response.data[0]["uuid"]

    # 3. ai_answer_messages 저장 (is_summary=False: 일반 응답)
    ai_response = self.supabase.table("ai_answer_messages").insert({
        "kakao_user_id": kakao_user_id,
        "content": ai_message,
        "is_summary": False  # 일반 대화는 False, 요약 메시지는 True
    }).execute()
    ai_uuid = ai_response.data[0]["uuid"]

    # 4. message_history에 턴 저장
    history_response = self.supabase.table("message_history").insert({
        "kakao_user_id": kakao_user_id,
        "user_answer_key": user_uuid,
        "ai_answer_key": ai_uuid,
        "session_date": session_date,
        "turn_index": turn_index
    }).execute()

    return {
        "history_uuid": history_response.data[0]["uuid"],
        "user_uuid": user_uuid,
        "ai_uuid": ai_uuid,
        "turn_index": turn_index
    }

# 저장 완료 후:
# - recent_conversations 뷰에서 자동으로 최근 5개 턴 조회 가능
# - daily_conversation_stats 뷰에서 통계 자동 반영
```

---

### 2. 대화 조회 로직

#### 2-1. 최근 N개 턴 조회 (RPC 함수 사용)

```python
async def get_recent_turns(
    self,
    kakao_user_id: str,
    limit: int = 5
) -> list[dict]:
    """
    최근 N개 대화 턴 조회

    Returns:
        [
            {
                "turn_index": 3,
                "user_message": "...",
                "ai_message": "...",
                "session_date": "2025-10-15",
                "created_at": "..."
            },
            ...
        ]
    """
    response = self.supabase.rpc(
        "get_recent_turns",
        {
            "p_kakao_user_id": kakao_user_id,
            "p_limit": limit
        }
    ).execute()

    return response.data
```

#### 2-2. 숏텀 메모리 조회 (최근 5개 턴)

```python
async def get_shortterm_memory(self, kakao_user_id: str) -> list[dict]:
    """
    최근 5개 턴 조회 (recent_conversations 뷰 사용)

    Returns:
        [
            {"user": "안녕", "ai": "안녕하세요"},
            {"user": "오늘 뭐했어", "ai": "..."},
            ...
        ]
    """
    response = self.supabase.table("recent_conversations") \
        .select("recent_turns") \
        .eq("kakao_user_id", kakao_user_id) \
        .execute()

    if response.data:
        return response.data[0]["recent_turns"]
    return []
```

#### 2-3. 오늘의 대화 조회

```python
async def get_today_conversations(self, kakao_user_id: str) -> list[dict]:
    """오늘 날짜의 모든 대화 턴 조회"""
    from datetime import date

    response = self.supabase.rpc(
        "get_turns_by_date",
        {
            "p_kakao_user_id": kakao_user_id,
            "p_session_date": str(date.today())
        }
    ).execute()

    return response.data
```

#### 2-4. 특정 날짜의 대화 조회

```python
async def get_conversations_by_date(
    self,
    kakao_user_id: str,
    target_date: str  # "2025-10-15"
) -> list[dict]:
    """특정 날짜의 대화 턴 조회"""
    response = self.supabase.rpc(
        "get_turns_by_date",
        {
            "p_kakao_user_id": kakao_user_id,
            "p_session_date": target_date
        }
    ).execute()

    return response.data
```

---

### 3. LLM 프롬프트용 히스토리 변환

#### ChatGPT/Claude 형식으로 변환

```python
async def get_conversation_history_for_llm(
    self,
    kakao_user_id: str,
    limit: int = 10
) -> list[dict]:
    """
    LLM API 호출용 대화 히스토리 변환

    Returns:
        [
            {"role": "user", "content": "안녕"},
            {"role": "assistant", "content": "안녕하세요"},
            ...
        ]
    """
    # 숏텀 메모리 조회 (최근 5개 턴)
    if limit <= 5:
        recent_turns = await self.get_shortterm_memory(kakao_user_id)

        # JSONB 형식 → LLM 형식 변환
        messages = []
        for turn in reversed(recent_turns):  # 오래된 순으로
            messages.append({"role": "user", "content": turn["user"]})
            messages.append({"role": "assistant", "content": turn["ai"]})

        return messages

    # 더 많은 히스토리 필요 시 DB 조회
    else:
        turns = await self.get_recent_turns(kakao_user_id, limit)

        messages = []
        for turn in reversed(turns):  # 오래된 순으로
            messages.append({"role": "user", "content": turn["user_message"]})
            messages.append({"role": "assistant", "content": turn["ai_message"]})

        return messages
```

---

### 4. daily_records와 연결

```python
async def save_daily_record_with_conversations(
    self,
    user_id: int,
    kakao_user_id: str,
    work_content: str,
    record_date: str
) -> dict:
    """
    일일 요약 저장 + 대화 턴 자동 연결

    트리거가 자동으로:
    1. 해당 날짜의 message_history에 daily_record_id 연결
    2. message_count 업데이트
    """
    response = self.supabase.table("daily_records").insert({
        "user_id": user_id,
        "work_content": work_content,
        "record_date": record_date
    }).execute()

    daily_record_id = response.data[0]["id"]

    # 연결된 대화 턴 조회
    linked_turns = self.supabase.table("message_history") \
        .select("*") \
        .eq("daily_record_id", daily_record_id) \
        .execute()

    return {
        "daily_record": response.data[0],
        "linked_turn_count": len(linked_turns.data)
    }
```

---

## 🔄 실전 사용 예시

### 시나리오 1: 챗봇 대화 흐름

```python
# chatbot/nodes.py 또는 적절한 위치

async def handle_user_message(state: State, db: SupabaseDatabase):
    kakao_user_id = state["kakao_user_id"]
    user_input = state["user_input"]

    # 1. 숏텀 메모리 조회 (최근 5개 턴)
    history = await db.get_conversation_history_for_llm(
        kakao_user_id,
        limit=5
    )

    # 2. LLM 호출
    messages = [
        {"role": "system", "content": "당신은 3분 커리어 챗봇입니다."},
        *history,
        {"role": "user", "content": user_input}
    ]

    ai_response = await call_llm(messages)

    # 3. 대화 턴 저장 (user + ai 쌍)
    turn_info = await db.save_conversation_turn(
        kakao_user_id=kakao_user_id,
        user_message=user_input,
        ai_message=ai_response
    )

    # 저장 후 recent_conversations 뷰에서 자동으로 최신 5개 턴 조회 가능!

    return {
        "ai_response": ai_response,
        "turn_index": turn_info["turn_index"]
    }
```

### 시나리오 2: 일일 요약 생성 시 대화 참조

```python
async def generate_daily_summary(kakao_user_id: str, db: SupabaseDatabase):
    from datetime import date

    # 1. 오늘의 모든 대화 조회
    today_conversations = await db.get_today_conversations(kakao_user_id)

    # 2. 대화 내용을 바탕으로 요약 생성
    conversation_text = "\n".join([
        f"User: {turn['user_message']}\nAI: {turn['ai_message']}"
        for turn in today_conversations
    ])

    summary = await generate_summary_with_llm(conversation_text)

    # 3. daily_record 저장 (트리거가 자동으로 대화 턴 연결)
    user_id = await db.get_user_id_by_kakao_id(kakao_user_id)

    result = await db.save_daily_record_with_conversations(
        user_id=user_id,
        kakao_user_id=kakao_user_id,
        work_content=summary,
        record_date=str(date.today())
    )

    return result
```

### 시나리오 3: 주간 요약 생성 시 대화 히스토리 활용

```python
async def generate_weekly_summary(kakao_user_id: str, db: SupabaseDatabase):
    # 1. 최근 7일간의 daily_records 조회
    daily_records = await db.get_daily_records(
        kakao_user_id,
        limit=7
    )

    # 2. (선택) 각 daily_record에 연결된 원본 대화 조회
    detailed_conversations = []
    for record in daily_records:
        turns = self.supabase.table("message_history") \
            .select("*, user_answer_messages(*), ai_answer_messages(*)") \
            .eq("daily_record_id", record["id"]) \
            .execute()

        detailed_conversations.append({
            "date": record["record_date"],
            "summary": record["work_content"],
            "turns": turns.data
        })

    # 3. 주간 요약 생성
    weekly_summary = await generate_weekly_summary_with_llm(
        daily_records,
        detailed_conversations
    )

    return weekly_summary
```

---

## ⚡ 성능 최적화 팁

### 1. 숏텀 메모리 우선 사용

```python
# ❌ 나쁜 예: 항상 DB 조회
async def get_history_slow(kakao_user_id: str):
    return await db.get_recent_turns(kakao_user_id, limit=5)

# ✅ 좋은 예: 캐싱 테이블 활용
async def get_history_fast(kakao_user_id: str):
    return await db.get_shortterm_memory(kakao_user_id)
```

### 2. 배치 조회

```python
# ❌ 나쁜 예: 여러 번 조회
for user_id in user_ids:
    turns = await db.get_recent_turns(user_id)

# ✅ 좋은 예: 한 번에 조회
response = self.supabase.table("message_history") \
    .select("*, user_answer_messages(*), ai_answer_messages(*)") \
    .in_("kakao_user_id", user_ids) \
    .order("created_at", desc=True) \
    .execute()
```

### 3. 필요한 컬럼만 조회

```python
# ❌ 나쁜 예: 전체 조회
response = self.supabase.table("message_history").select("*")

# ✅ 좋은 예: 필요한 컬럼만
response = self.supabase.table("message_history") \
    .select("uuid, user_answer_key, ai_answer_key")
```

---

## 🧪 마이그레이션 체크리스트

### 1. 마이그레이션 전

- [ ] `db_schema_v2.sql` 검토
- [ ] 개발 환경에서 테스트
- [ ] 기존 `ai_conversations` 백업

### 2. 마이그레이션 실행

```sql
-- Supabase SQL Editor에서 실행

-- 1. 스키마 생성
\i db_schema_v2.sql

-- 2. 기존 데이터 마이그레이션
SELECT migrate_ai_conversations_to_v2();

-- 3. 검증
SELECT
    ac.kakao_user_id,
    jsonb_array_length(ac.conversation_history) / 2 as original_turn_count,
    COUNT(mh.id) as migrated_turn_count
FROM ai_conversations ac
LEFT JOIN message_history mh ON mh.kakao_user_id = ac.kakao_user_id
GROUP BY ac.kakao_user_id, ac.conversation_history;
```

### 3. 스키마 업데이트 (최신 V2)

- [ ] `update_recent_conversations_to_view.sql` 실행
  - [ ] `conversation_history_view` 삭제
  - [ ] `recent_conversations` 테이블 → 뷰로 변경
  - [ ] 트리거 및 함수 삭제

### 4. Python 코드 수정

- [ ] `database.py` 수정
  - [ ] `save_conversation_turn()` 구현 (is_summary 필드 추가)
  - [ ] `get_recent_turns()` 구현
  - [ ] `get_shortterm_memory()` 구현
  - [ ] `get_conversation_history_for_llm()` 구현
- [ ] `chatbot/nodes.py` 수정
  - [ ] 대화 저장 로직 변경
  - [ ] 히스토리 조회 로직 변경
- [ ] 단위 테스트 작성
- [ ] 통합 테스트

### 5. 배포

- [ ] 프로덕션 DB 백업
- [ ] 마이그레이션 스크립트 실행
- [ ] 애플리케이션 배포
- [ ] 모니터링

### 6. 사후 작업

- [ ] 성능 모니터링
- [ ] 기존 `ai_conversations` 백업 후 삭제
- [ ] 문서 업데이트

---

## 📊 AS-IS vs TO-BE 비교

| 작업 | AS-IS (JSONB 배열) | TO-BE (정규화 V2) |
|------|-------------------|------------------|
| **메시지 저장** | JSON 배열 전체 읽기/쓰기 | 3개 테이블 INSERT만 |
| **최근 5개 턴 조회** | 전체 배열 파싱 | 뷰 1회 조회 (실시간) |
| **특정 날짜 조회** | 불가능 (전체 파싱) | 인덱스 활용 조회 |
| **메시지 카운트** | 애플리케이션에서 계산 | COUNT 쿼리 (message_history) |
| **요약 메시지 구분** | 불가능 | is_summary 필드로 구분 |
| **보안** | 내용 노출 | UUID 키로 참조 |
| **확장성** | JSON 크기 제한 | 무제한 |

---

## 🎯 결론

V2 스키마로 개선하면:
- ✅ **속도**: recent_conversations 뷰로 최근 5개 턴 즉시 조회
- ✅ **보안**: UUID 키값으로 간접 참조
- ✅ **유연성**: 날짜별, 턴별, 요약별 조회 가능
- ✅ **확장성**: 테이블 분리로 무제한 확장
- ✅ **일관성**: 뷰 기반으로 항상 최신 데이터 보장
- ✅ **유지보수**: 트리거 없이 뷰만으로 자동 업데이트

질문이나 추가 지원이 필요하면 말씀해주세요! 😊
