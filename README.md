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

- **Backend**: Python 3.11+ + FastAPI
- **AI Framework**: LangChain + LangGraph
- **LLM**: OpenAI GPT-3.5-turbo
- **Database**: Supabase (PostgreSQL)
- **Package Manager**: Poetry
- **Web Server**: Uvicorn
- **Messaging**: KakaoTalk Bot API

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

# 서버 설정 (선택사항)
PORT=8000
```

### 5. 서버 실행

```bash
# Poetry 환경에서 실행
poetry run python main.py

# 또는 Poetry shell 활성화 후 실행
poetry shell
python main.py

# 직접 uvicorn 사용
poetry run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

서버가 성공적으로 시작되면 다음과 같은 메시지가 표시됩니다:

```
✅ Supabase 클라이언트 초기화 성공
✅ 시스템 프롬프트 로드 성공
✅ 유저 프롬프트 템플릿 로드 성공
✅ SimpleChatBot 초기화 완료
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 6. 웹 인터페이스 접속

브라우저에서 `http://localhost:8000`에 접속하여 테스트 페이지를 확인할 수 있습니다.

## 📁 프로젝트 구조

```
kakao-work-bot/
├── main.py                 # FastAPI 메인 애플리케이션
├── pyproject.toml         # Poetry 프로젝트 설정
├── poetry.lock           # Poetry 의존성 잠금 파일
├── prompt.text           # AI 프롬프트 설정
├── .env                  # 환경 변수 (git에서 제외)
├── .env.example          # 환경 변수 예시 파일
├── README.md            # 프로젝트 문서
├── src/                 # 소스 코드
│   ├── chatbot/         # 챗봇 관련 모듈
│   │   ├── __init__.py
│   │   ├── simple_chatbot.py    # 메인 챗봇 클래스
│   │   ├── memory_manager.py    # 대화 메모리 관리
│   │   ├── utils.py            # 유틸리티 함수들
│   │   └── state.py            # 대화 상태 관리
│   └── database.py      # 데이터베이스 연결 및 쿼리
├── public/              # 정적 웹 파일
│   ├── index.html       # 테스트 웹 페이지
│   ├── style.css        # 스타일시트
│   └── script.js        # 클라이언트 스크립트
└── archive/             # 아카이브 파일들
```

## 🗄️ 데이터베이스 구조

### 테이블 스키마

#### 1. `users` 테이블

```sql
CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  kakao_user_id VARCHAR(255) UNIQUE NOT NULL,
  name VARCHAR(100),
  job_title VARCHAR(200),
  total_years VARCHAR(50),
  job_years VARCHAR(50),
  career_goal TEXT,
  project_name TEXT,
  recent_work TEXT,
  job_meaning TEXT,
  important_thing TEXT,
  onboarding_completed BOOLEAN DEFAULT FALSE,
  attendance_count INTEGER DEFAULT 0,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### 2. `conversation_states` 테이블

```sql
CREATE TABLE conversation_states (
  id SERIAL PRIMARY KEY,
  kakao_user_id VARCHAR(255) NOT NULL,
  current_step VARCHAR(100),
  temp_data JSONB DEFAULT '{}',
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### 3. `conversation_history` 테이블

```sql
CREATE TABLE conversation_history (
  id SERIAL PRIMARY KEY,
  user_id VARCHAR(255) NOT NULL,
  role VARCHAR(50) NOT NULL,
  content TEXT NOT NULL,
  timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### 데이터베이스 설정

1. Supabase 프로젝트 생성
2. SQL Editor에서 위 스키마 실행
3. Row Level Security (RLS) 정책 설정
4. API 키 및 URL을 `.env` 파일에 설정

## 🔧 핵심 컴포넌트

### 1. SimpleChatBot (`src/chatbot/simple_chatbot.py`)

메인 챗봇 클래스로 다음 기능을 담당합니다:

- LangChain 기반 대화 처리
- OpenAI GPT API 호출
- 대화 히스토리 관리
- 응답 캐싱 및 최적화

### 2. MemoryManager (`src/chatbot/memory_manager.py`)

대화 메모리 관리를 담당합니다:

- 대화 히스토리 저장/조회
- 응답 캐싱
- 메모리 최적화

### 3. Database (`src/database.py`)

Supabase 데이터베이스 연동을 담당합니다:

- 사용자 정보 관리
- 대화 기록 저장
- 온보딩 상태 관리

### 4. PromptLoader (`src/chatbot/utils.py`)

AI 프롬프트 관리를 담당합니다:

- 프롬프트 파일 로드
- 동적 프롬프트 구성
- 폴백 프롬프트 제공

## 🚀 API 엔드포인트

### 웹 인터페이스

- `GET /` - 메인 테스트 페이지
- `GET /style.css` - 스타일시트
- `GET /script.js` - 클라이언트 스크립트

### API 엔드포인트

- `GET /api/status` - 서버 상태 확인
- `POST /webhook` - 카카오톡 웹훅 (구현 예정)
- `POST /api/chat` - 직접 채팅 API (구현 예정)

## 🎯 AI 시스템 특징

### 프롬프트 시스템

`prompt.text` 파일에서 AI의 성격과 응답 패턴을 정의합니다:

- **역할**: 3분커리어 AI 에이전트
- **응답 구조**: 공감 → 질문 → 정리
- **언어**: 한국어 자연스러운 대화 스타일
- **목표**: 커리어 발전 도움

### 성능 최적화

1. **토큰 절약**:
   - 대화 히스토리 제한 (최근 6개 메시지)
   - 메시지 길이 제한 (300자)
   - max_tokens 설정 (300)

2. **응답 캐싱**:
   - 동일한 질문에 대한 중복 API 호출 방지
   - 메모리 기반 캐싱 시스템

3. **비동기 처리**:
   - FastAPI의 async/await 활용
   - 데이터베이스 쿼리 최적화

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

### 로컬 배포

```bash
# 프로덕션 모드로 실행
poetry run uvicorn main:app --host 0.0.0.0 --port 8000
```

### 클라우드 배포

1. **Heroku 배포**:
   ```bash
   # Procfile 생성
   echo "web: uvicorn main:app --host=0.0.0.0 --port=${PORT:-8000}" > Procfile
   ```

2. **Docker 배포**:
   ```dockerfile
   FROM python:3.11-slim
   WORKDIR /app
   COPY pyproject.toml poetry.lock ./
   RUN pip install poetry && poetry install --no-root
   COPY . .
   CMD ["poetry", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
   ```

## 📈 향후 개발 계획

- [ ] 카카오톡 웹훅 연동 완성
- [ ] 온보딩 플로우 구현
- [ ] LangGraph 기반 복잡한 대화 흐름
- [ ] 다양한 AI 모델 지원
- [ ] 대화 분석 및 인사이트 기능
- [ ] 모바일 앱 연동

## 📞 지원 및 문의

### 유용한 링크

- [FastAPI 문서](https://fastapi.tiangolo.com/)
- [LangChain 문서](https://python.langchain.com/)
- [Supabase 문서](https://supabase.com/docs)
- [OpenAI API 문서](https://platform.openai.com/docs)
- [Poetry 문서](https://python-poetry.org/docs/)

---

**3분 커리어와 함께 성장하세요!** 🚀