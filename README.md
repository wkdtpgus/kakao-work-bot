# 🚀 3분 커리어 - 카카오톡 챗봇

Python FastAPI와 LangChain을 기반으로 한 AI 대화형 커리어 챗봇 서비스입니다.

## 📋 프로젝트 개요

### 주요 기능

- **AI 대화 시스템**: LangChain과 OpenAI GPT를 활용한 자연스러운 대화
- **커리어 컨설팅**: 업무 경험 정리 및 커리어 조언 제공
- **카카오톡 연동**: 웹훅 기반 메시지 처리
- **데이터 관리**: Supabase를 통한 사용자 정보 및 대화 기록 저장
- **웹 인터페이스**: 테스트용 웹 페이지 제공

### 기술 스택

- **Backend**: Python 3.12+ + FastAPI
- **AI Framework**: LangChain + LangGraph (멀티 스텝 워크플로우)
- **LLM**:
  - 온보딩: gpt-4o-mini (max_tokens: 500)
  - 일일기록/주간피드백: gpt-4o-mini (max_tokens: 800)
- **Database**: Supabase (PostgreSQL)
- **Package Manager**: Poetry 2.2+
- **Web Server**: Uvicorn (ASGI)
- **Monitoring**: LangSmith (추적 및 디버깅)
- **Messaging**: KakaoTalk Bot API
- **Deployment**: AWS EC2 (Ubuntu 24.04)

## 🛠️ 개발 환경 설정

### 사전 요구사항

- Python 3.11 이상
- Poetry (Python 패키지 관리도구)

### 1. 저장소 클론

```bash
git clone <repository-url>
cd kakao-work-bot
```

### 2. Poetry 설치 (없는 경우)

```bash
# macOS/Linux
curl -sSL https://install.python-poetry.org | python3 -

# Windows (PowerShell)
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -
```

### 3. 의존성 설치

```bash
# Poetry를 사용한 의존성 설치
poetry install --no-root

# 또는 pip 사용 (권장하지 않음)
pip install -r requirements.txt
```

### 4. 환경 변수 설정

`.env` 파일을 생성하고 다음 변수들을 설정하세요:

```env
# Supabase 설정
SUPABASE_URL=your_supabase_project_url
SUPABASE_ANON_KEY=your_supabase_anon_key

# OpenAI API 설정
OPENAI_API_KEY=your_openai_api_key

# LangSmith 추적 (선택사항)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_API_KEY=your_langsmith_api_key
LANGCHAIN_PROJECT=3min_career

# 서버 설정
PORT=8000
```

### 5. 서버 실행

```bash
# Poetry 환경에서 실행 (권장)
poetry run python main.py

# 직접 uvicorn 사용
poetry run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**참고**: Poetry 2.0+부터 `poetry shell` 명령어가 기본 제공되지 않습니다. `poetry run` 사용을 권장합니다.

서버가 성공적으로 시작되면 다음과 같은 메시지가 표시됩니다:

```
✅ Supabase 클라이언트 초기화 성공
INFO:     Started server process [PID]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### 6. 웹 인터페이스 접속

브라우저에서 `http://localhost:8000`에 접속하여 테스트 페이지를 확인할 수 있습니다.

## 📁 프로젝트 구조

```
kakao-work-bot/
├── main.py                 # FastAPI 메인 애플리케이션
├── pyproject.toml         # Poetry 프로젝트 설정
├── poetry.lock           # Poetry 의존성 잠금 파일
├── .env                  # 환경 변수 (git에서 제외)
├── .env.example          # 환경 변수 예시 파일
├── README.md            # 프로젝트 문서
├── src/
│   ├── chatbot/              # 챗봇 핵심 모듈
│   │   ├── __init__.py
│   │   ├── graph_manager.py  # LangGraph 워크플로우 관리
│   │   ├── workflow.py       # 멀티 스텝 워크플로우 정의
│   │   ├── nodes.py          # 노드 함수들 (router, onboarding, daily, weekly)
│   │   ├── state.py          # 상태 정의 (Pydantic 모델)
│   │   └── memory_manager.py # 대화 메모리 관리
│   ├── database/             # 데이터베이스 레이어 (Repository Pattern)
│   │   ├── __init__.py
│   │   ├── database.py       # Supabase 저수준 CRUD
│   │   ├── schemas.py        # Pydantic 스키마 (타입 안정성)
│   │   ├── user_repository.py         # 사용자 관련 복합 쿼리
│   │   ├── conversation_repository.py # 대화 상태 관리
│   │   └── summary_repository.py      # 요약 저장 로직
│   ├── service/              # 서비스 레이어
│   │   ├── intent_classifier.py       # 사용자 의도 분류
│   │   ├── summary_generator.py       # 일일 요약 생성
│   │   └── weekly_feedback_generator.py # 주간 피드백 생성
│   ├── prompt/               # AI 프롬프트 모음
│   │   ├── onboarding.py     # 온보딩 프롬프트
│   │   ├── daily_record_prompt.py    # 일일기록 프롬프트
│   │   ├── daily_summary_prompt.py   # 일일요약 프롬프트
│   │   ├── weekly_summary_prompt.py  # 주간요약 프롬프트
│   │   └── intent_classifier.py      # 의도 분류 프롬프트
│   ├── config/              # 설정 파일
│   │   └── config.py        # 모델 설정 (max_tokens, timeout 등)
│   └── utils/               # 유틸리티
│       ├── utils.py         # 헬퍼 함수들
│       └── models.py        # LLM 설정
├── public/                  # 정적 웹 파일
│   ├── index.html          # 테스트 웹 페이지
│   ├── style.css           # 스타일시트
│   └── script.js           # 클라이언트 스크립트
└── supabase_migration.sql  # DB 마이그레이션 스크립트
```

## 🗄️ 데이터베이스 구조

### 테이블 개요

| 테이블 | 설명 | 주요 컬럼 |
|--------|------|-----------|
| `users` | 사용자 프로필 | 온보딩 9개 필드, `daily_record_count` (7일 카운터) |
| `conversation_states` | 대화 상태 | `current_step`, `temp_data` (JSONB) |
| `ai_conversations` | 대화 히스토리 | `conversation_history` (JSONB 배열) |
| `daily_records` | 일일 요약 | `work_content`, `record_date` (unique) |
| `weekly_summaries` | 주간 요약 | `sequence_number`, `summary_content` |

### 데이터베이스 설정

1. Supabase 프로젝트 생성
2. SQL Editor에서 마이그레이션 스크립트 실행:
   ```bash
   # 기본 테이블 생성
   supabase_migration.sql

   # daily_records 관련 컬럼 추가
   supabase_migration_daily_records.sql
   ```
3. Row Level Security (RLS) 정책 설정 (선택)
4. API 키 및 URL을 `.env` 파일에 설정

> 📝 상세한 스키마 정의는 `supabase_migration.sql` 파일을 참고하세요.

## 🔧 핵심 컴포넌트

### 1. GraphManager (`src/chatbot/graph_manager.py`)

LangGraph 워크플로우 관리자:

- 유저별 그래프 인스턴스 관리
- LLM 설정 (온보딩/서비스 분리)
- 대화 처리 진입점 (handle_conversation)

### 2. Workflow (`src/chatbot/workflow.py`)

멀티 스텝 워크플로우 정의:

```
START
  │
  ▼
router_node (온보딩 완료 체크)
  ├── 온보딩 미완료 → onboarding_agent_node
  │                   ├── 9개 필드 수집
  │                   ├── 3회 시도 제한
  │                   ├── field_status 추적
  │                   └── END
  │
  └── 온보딩 완료 → service_router_node (의도 분류 - LLM)
      ├── daily_record → daily_agent_node
      ├── rejection (주간 요약 거절) → daily_agent_node
      │   └── classify_user_intent (재분류)
      │       ├── summary (요약 생성)
      │       │   ├── daily_records 저장
      │       │   ├── daily_record_count 증가
      │       │   └── 7일차 체크
      │       │       ├── Yes → weekly_summary_ready=True → temp_data 저장 → END
      │       │       └── No → END
      │       │
      │       ├── rejection (요약 거절) → 세션 초기화 → END
      │       ├── restart (재시작) → 세션 초기화 → END
      │       │
      │       └── continue (일반 대화)
      │           └── 대화 횟수 카운팅
      │               ├── 5회 이상 → 요약 제안 → END
      │               └── 5회 미만 → 질문 생성 → END
      │
      └── weekly_feedback/weekly_acceptance → weekly_agent_node
          ├── 7일차 자동: daily_records 7개 조회 → weekly_summaries 저장 → 카운터 리셋
          └── 수동 요청: 7일 미달 → 참고용만 제공
          └── END
```

### 3. 노드별 상세 설명

#### 📍 **router_node** - 온보딩 완료 체크

**입력**: 사용자 메시지, `user_id`

**처리**:
1. `users` 테이블에서 사용자 정보 조회
2. 9개 필수 필드 체크 (`name`, `job_title`, `total_years`, `job_years`, `career_goal`, `project_name`, `recent_work`, `job_meaning`, `important_thing`)
3. `conversation_states.temp_data`에서 세션 상태 복원

**출력**:
- 온보딩 미완료 → `onboarding_agent_node`
- 온보딩 완료 → `service_router_node`

**DB 접근**:
- 조회: `users`, `conversation_states`

---

#### 📍 **onboarding_agent_node** - 온보딩 정보 수집

**입력**: 사용자 메시지, `user_context`

**처리**:
1. 최근 3개 대화 로드 (이름 확인 플로우)
2. 현재 타겟 필드 결정 (null 필드 중 첫 번째)
3. LLM Structured Output으로 정보 추출
4. 필드별 시도 횟수 추적 (`field_attempts`)
5. 3회 시도 실패 시 `[INSUFFICIENT]` 또는 `skipped` 처리
6. 온보딩 완료 시 대화 히스토리 초기화

**출력**: 온보딩 완료 메시지 → END

**DB 접근**:
- 저장: `users` (9개 필드)
- 저장: `conversation_states.temp_data` (field_attempts, field_status)
- 저장: `ai_conversations` (대화 저장)

---

#### 📍 **service_router_node** - 사용자 의도 분류

**입력**: 사용자 메시지, `user_context`

**처리**:
1. LLM으로 의도 분류 (SERVICE_ROUTER_USER_PROMPT)
   - `daily_record`: 일일 업무 기록
   - `weekly_feedback`: 주간 요약 명시 요청
   - `weekly_acceptance`: 7일차 주간 요약 수락
   - `rejection`: 거절 → 플래그 정리

**출력**:
- `daily_record` / `rejection` → `daily_agent_node`
- `weekly_feedback` / `weekly_acceptance` → `weekly_agent_node`

**DB 접근**:
- 조회/저장: `conversation_states.temp_data` (플래그 정리)
- 저장: `ai_conversations` (대화 저장)

---

#### 📍 **daily_agent_node** - 일일 기록 처리

**입력**: 사용자 메시지, `user_context`

**처리**:
1. 최신 20개 대화 로드 (Repository: `get_today_conversations`)
2. `classify_user_intent`로 재분류:
   - **`summary`**: 데일리 요약 생성 요청
     - 최신 10개 대화 기반 요약 생성
     - `daily_records` 테이블에 저장 (오늘 날짜)
     - Repository: `increment_counts_with_check` (daily_record_count + attendance_count)
     - **7일차 체크** (`attendance_count % 7 == 0`):
       - Yes → Repository: `set_weekly_summary_flag` + "🎉 7일차 달성! 주간 요약도 보여드릴까요?"
       - No → 일반 요약 완료 메시지
   - **`edit_summary`**: 요약 수정 요청 (2025-01 추가)
     - **현재 메시지를 포함**해서 요약 재생성
     - 수정 내용이 반영된 새 요약 제공
   - **`rejection`**: 요약 제안 거절
     - 세션 초기화 (`daily_session_data = {}`)
     - "알겠습니다, 다시 시작할 때 편하게 말씀해주세요"
   - **`restart`**: 새 일일 기록 시작
     - 세션 초기화
     - "새로운 일일 기록을 시작하겠습니다! 오늘은 어떤 업무를 하셨나요?"
   - **`continue`**: 일반 대화 (기본값)
     - 대화 횟수 카운팅 (`conversation_count`)
     - **5회 이상** → "지금까지 내용을 정리해드릴까요?" 요약 제안
     - **5회 미만** → 프롬프트 기반 질문 생성

**출력**: AI 응답 → END

**DB 접근**:
- 조회: `ai_conversations` (대화 히스토리)
- 저장: `daily_records` (summary일 때만)
- 업데이트: `users.daily_record_count` (summary일 때만)
- 저장: `conversation_states.temp_data` (세션 데이터, 플래그)
- 저장: `ai_conversations` (대화 저장)

---

#### 📍 **weekly_agent_node** - 주간 피드백 생성

**입력**: 사용자 메시지, `user_context`

**처리**:
1. `conversation_states.temp_data`에서 플래그 확인
2. **7일차 자동 트리거** (`weekly_summary_ready=True`):
   - `daily_records`에서 최근 7개 조회
   - 주간 피드백 생성 (LLM)
   - `weekly_summaries` 테이블에 저장
   - `users.daily_record_count` = 0 (리셋)
   - 플래그 정리 (`weekly_summary_ready`, `daily_count` 제거)
3. **수동 요청**:
   - 7일 미달 → 참고용 피드백 (DB 저장 X)
   - 7일 달성 but 플래그 없음 → "이미 확인" 메시지

**출력**: 주간 피드백 텍스트 → END

**DB 접근**:
- 조회: `conversation_states.temp_data`, `users`, `daily_records`
- 저장: `weekly_summaries` (주간 요약 저장)
- 업데이트: `users.daily_record_count` (리셋)
- 저장: `conversation_states.temp_data` (플래그 정리)
- 저장: `ai_conversations` (대화 저장)

### 4. MemoryManager (`src/chatbot/memory_manager.py`)

대화 메모리 관리:

- 대화 히스토리 저장/조회 (Supabase)
- 요약 생성 (긴 대화 압축)
- 최근 10개 메시지 유지

### 5. Database Layer (`src/database/`)

**Repository Pattern 적용으로 DB 로직 모듈화:**

#### 구조
- **`database.py`**: Supabase 저수준 CRUD 메서드
- **`schemas.py`**: Pydantic 타입 안정성 스키마
- **`user_repository.py`**: 사용자 관련 복합 쿼리 (6개 함수)
- **`conversation_repository.py`**: 대화 상태 관리 (5개 함수)
- **`summary_repository.py`**: 요약 저장 로직 (3개 함수)

#### State 캐싱 (2025-01 적용)
- `router_node`에서 최초 조회 → State에 캐싱
- 이후 노드들은 캐시된 데이터 재사용
- **DB 쿼리 50% 감소** (6→3 쿼리)

#### 주요 Repository 함수
- `get_user_with_context`: 사용자 정보 + 메타데이터 한 번에 조회
- `check_and_reset_daily_count`: 날짜 변경 시 자동 리셋
- `increment_counts_with_check`: 카운트 증가 + 5일차 자동 체크
- `save_onboarding_metadata`: 온보딩 데이터 저장 (users + conversation_states)
- `get_today_conversations`: 오늘 대화 + conv_state 병렬 조회
- `set_weekly_summary_flag`: 7일차 플래그 설정
- `save_weekly_summary_with_metadata`: 주간 요약 자동 저장

## 🚀 API 엔드포인트

### 웹 인터페이스

- `GET /` - 메인 테스트 페이지
- `GET /style.css` - 스타일시트
- `GET /script.js` - 클라이언트 스크립트

### API 엔드포인트

- `GET /api/status` - 서버 상태 확인
- `POST /webhook` - 카카오톡 웹훅 (메인 진입점)
- `POST /api/chat` - 웹 테스트용 채팅 API
- `GET /api/user/{user_id}` - 사용자 정보 조회

## 🎯 AI 시스템 특징

### 프롬프트 시스템

각 노드별로 최적화된 프롬프트를 사용합니다:

- **온보딩 프롬프트** (`src/prompt/onboarding.py`):
  - 9개 필드 수집 (이름, 직무, 연차, 목표 등)
  - 간소화된 구조 (57줄, 토큰 효율)
  - 첫 사용자 환영 메시지

- **일일 기록 프롬프트** (`src/prompt/daily_record_prompt.py`):
  - 업무 경험 대화형 수집
  - 공감 + 경청 스타일

- **요약 프롬프트** (`src/prompt/daily_summary_prompt.py`):
  - 일일 대화 요약 생성
  - 핵심 내용 추출

- **주간 피드백 프롬프트** (`src/prompt/weekly_summary_prompt.py`):
  - 일주일 활동 분석
  - 성장 포인트 및 제안 제공

### 성능 최적화

1. **프롬프트 최적화** (2025-01 적용):
   - 온보딩 프롬프트 70% 간소화 (191줄 → 57줄)
   - 토큰 수 대폭 감소: 3,295 → 약 1,200 토큰

2. **토큰 제한**:
   - 온보딩 Agent: max_tokens=500 (응답 간결화)
   - 일일/주간 Agent: max_tokens=800
   - 대화 히스토리: 최근 10개 메시지만 유지
   - 메시지 길이 제한: 300자

3. **Timeout 설정**:
   - LLM Timeout: 10초 (기존 30초에서 단축)
   - 응답 시간: 평균 2-4초 (목표 3초 이하)

4. **비동기 처리**:
   - FastAPI의 async/await 전면 활용
   - Supabase 쿼리 비동기 처리
   - LLM 호출 비동기화

5. **모니터링**:
   - LangSmith 추적으로 병목 지점 실시간 파악
   - 노드별 실행 시간 측정

## 🔒 보안 고려사항

### API 키 보안

- `.env` 파일을 `.gitignore`에 포함
- 환경 변수로 민감 정보 관리
- 프로덕션 환경에서 환경 변수 암호화

### 데이터 보호

- Supabase RLS (Row Level Security) 활용
- 사용자 데이터 암호화
- 정기적인 보안 감사

## 🧪 테스트 및 디버깅

### 로컬 테스트

1. 서버 실행 후 `http://localhost:8000` 접속
2. 테스트 페이지에서 메시지 입력
3. 콘솔 로그로 처리 과정 확인

### 로그 모니터링

- `✅` : 성공적인 작업
- `⚠️` : 경고 (폴백 동작)
- `❌` : 오류 발생
- `🤖` : AI 관련 처리

### 일반적인 문제 해결

1. **환경 변수 오류**: `.env` 파일 확인
2. **Poetry 설치 문제**: `poetry install --no-root` 사용
3. **포트 충돌**: 다른 포트 사용 (`--port 8001`)
4. **AI 응답 오류**: OpenAI API 키 및 크레딧 확인

## 📦 의존성 정보

주요 패키지들:

- **fastapi**: 웹 프레임워크
- **uvicorn**: ASGI 서버
- **langchain**: AI 프레임워크
- **langchain-openai**: OpenAI 연동
- **supabase**: 데이터베이스 클라이언트
- **python-dotenv**: 환경 변수 로드

## 🚀 배포 가이드

### EC2 배포 (Production)

현재 프로젝트는 AWS EC2 (Ubuntu 24.04)에 배포되어 있습니다.

#### 1. EC2 인스턴스 설정

```bash
# SSH 접속
ssh -i ~/path/to/key.pem ubuntu@<EC2-IP>

# 시스템 패키지 업데이트
sudo apt update && sudo apt install -y python3-pip python3-venv curl

# Poetry 설치
curl -sSL https://install.python-poetry.org | python3 -
echo 'export PATH="/home/ubuntu/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

#### 2. 프로젝트 배포

```bash
# GitHub에서 클론 (SSH 키 설정 필요)
git clone git@github.com:your-username/kakao-work-bot.git
cd kakao-work-bot

# .env 파일 업로드 (로컬에서)
scp -i ~/path/to/key.pem .env ubuntu@<EC2-IP>:~/kakao-work-bot/.env

# 의존성 설치
poetry install

# 서버 실행
poetry run python main.py
```

#### 3. Security Group 설정

- 포트 22 (SSH)
- 포트 80 (HTTP) 또는 8000 (개발)
- 포트 443 (HTTPS)

#### 4. 재배포 프로세스

```bash
# 로컬에서 변경사항 푸시
git add .
git commit -m "변경 내용"
git push origin main

# EC2에서 업데이트
cd ~/kakao-work-bot
git pull
# Ctrl+C로 서버 종료
poetry run python main.py
```

#### 5. 백그라운드 실행 (tmux 사용)

```bash
# tmux 세션 생성
tmux new -s chatbot
poetry run python main.py

# Detach: Ctrl+B, D
# 재접속: tmux attach -t chatbot
```

### Docker 배포 (선택사항)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry install --no-root
COPY . .
CMD ["poetry", "run", "python", "main.py"]
```

## 📈 향후 개발 계획

### 완료 ✅
- [x] 카카오톡 웹훅 연동
- [x] 온보딩 플로우 (9개 필드 수집)
- [x] LangGraph 멀티 스텝 워크플로우
- [x] 일일 기록 및 요약 기능
- [x] 주간 피드백 생성
- [x] LangSmith 모니터링
- [x] EC2 프로덕션 배포
- [x] 성능 최적화 (응답 2-4초)
- [x] **Repository Pattern 도입** (2025-01)
- [x] **State 캐싱으로 DB 쿼리 50% 감소** (2025-01)
- [x] **요약 수정 기능 (edit_summary)** (2025-01)

### 진행 중 🚧
- [ ] 응답 속도 3초 이하 최적화
- [ ] 주간 요약 테이블 생성
- [ ] 온보딩 첫 사용자 환영 메시지 개선

### 계획 📋
- [ ] systemd 서비스 등록 (서버 자동 재시작)
- [ ] Nginx 리버스 프록시 (포트 80 → 8000)
- [ ] HTTPS 설정 (Let's Encrypt)
- [ ] 대화 분석 대시보드

## 📞 지원 및 문의

### 유용한 링크

- [FastAPI 문서](https://fastapi.tiangolo.com/)
- [LangChain 문서](https://python.langchain.com/)
- [Supabase 문서](https://supabase.com/docs)
- [OpenAI API 문서](https://platform.openai.com/docs)
- [Poetry 문서](https://python-poetry.org/docs/)

---

**3분 커리어와 함께 성장하세요!** 🚀