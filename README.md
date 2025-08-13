# 🚀 3분 커리어 - 카카오톡 챗봇

카카오톡을 통해 사용자의 일일 업무 경험을 AI Agent와 함께 정리하고, 커리어 성장을 돕는 챗봇 서비스입니다.

## 📋 프로젝트 개요

### 주요 기능
- **온보딩 시스템**: 사용자 정보 수집 및 프로필 설정
- **AI Agent**: ChatGPT 기반 업무 경험 정리 및 커리어 조언
- **카카오톡 연동**: 웹훅 기반 메시지 처리
- **데이터베이스**: Supabase를 통한 사용자 정보 및 대화 기록 관리

### 기술 스택
- **Backend**: Node.js + Express.js
- **Database**: Supabase (PostgreSQL)
- **AI**: OpenAI GPT-3.5-turbo
- **Platform**: Vercel (Serverless)
- **Messaging**: KakaoTalk Bot API

## 🛠️ 개발 환경 설정

### 1. 저장소 클론
```bash
git clone <repository-url>
cd kakao-work-bot
```

### 2. 의존성 설치
```bash
npm install
```

### 3. 환경 변수 설정
`.env` 파일을 생성하고 다음 변수들을 설정하세요:

```env
# Supabase 설정
SUPABASE_URL=your_supabase_project_url
SUPABASE_ANON_KEY=your_supabase_anon_key

# OpenAI API 설정
OPENAI_API_KEY=your_openai_api_key

# 서버 설정 (선택사항)
PORT=3000
```

### 4. 로컬 서버 실행
```bash
# 개발 모드
npm run dev

# 프로덕션 모드
npm start
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

### 데이터베이스 설정
1. Supabase 프로젝트 생성
2. SQL Editor에서 위 스키마 실행
3. Row Level Security (RLS) 정책 설정

## 🔧 주요 코드 구조

### 1. 메인 애플리케이션 (`index.js`)

#### 핵심 함수들
- **`handleOnboarding(userId, message)`**: 온보딩 프로세스 관리
- **`handleAIConversation(userId, message)`**: AI Agent 대화 처리
- **`callChatGPT(message, conversationHistory)`**: OpenAI API 호출
- **`processAIAgentResponse(userId, message)`**: 비동기 AI 응답 처리

#### 웹훅 엔드포인트
```javascript
app.post('/webhook', async (req, res) => {
  // 카카오톡 웹훅 요청 처리
  // 사용자 메시지 및 액션 분석
  // 상태별 처리 분기
});
```

### 2. 프롬프트 시스템 (`prompt.text`)
- **AI_AGENT_SYSTEM_PROMPT**: AI Agent의 역할과 성격 정의
- **AI_AGENT_USER_PROMPT_TEMPLATE**: 대화 컨텍스트 구성 템플릿

### 3. 온보딩 플로우
```
온보딩 시작 → 이름 입력 → 직무 입력 → 총 연차 → 직무 연차 → 
커리어 목표 → 프로젝트 정보 → 최근 업무 → 직무 의미 → 
중요한 가치 → 완료
```

## 🚀 배포 가이드

### Vercel 배포
1. Vercel 계정 생성 및 프로젝트 연결
2. 환경 변수 설정 (SUPABASE_URL, SUPABASE_ANON_KEY, OPENAI_API_KEY)
3. 자동 배포 설정

### 환경 변수 관리
- **로컬**: `.env` 파일 사용
- **프로덕션**: Vercel Dashboard에서 설정
- **보안**: API 키는 절대 Git에 커밋하지 마세요

## 🔍 디버깅 및 로깅

### 로그 레벨
- `📨 웹훅 요청 수신`: 요청 시작
- `🔍 현재 대화 상태`: 상태 확인
- `🤖 AI Agent`: AI 관련 처리
- `❌ 오류`: 에러 발생
- `✅ 성공`: 작업 완료

### 일반적인 문제 해결
1. **환경 변수 오류**: `.env` 파일 및 Vercel 설정 확인
2. **데이터베이스 연결 실패**: Supabase URL 및 키 확인
3. **AI 응답 타임아웃**: 토큰 수 및 모델 설정 조정

## 📱 카카오톡 연동

### 웹훅 설정
1. 카카오 비즈니스 계정에서 봇 생성
2. 웹훅 URL 설정: `https://your-domain.vercel.app/webhook`
3. 응답 타임아웃: 5초 (카카오 정책)

### 메시지 형식
```javascript
{
  version: "2.0",
  template: {
    outputs: [{
      simpleText: {
        text: "메시지 내용"
      }
    }],
    quickReplies: [
      {
        action: "message",
        label: "버튼 텍스트"
      }
    ]
  }
}
```

## 🎯 AI Agent 최적화

### 토큰 절약 전략
1. **대화 히스토리 제한**: 최근 6개 메시지만 유지
2. **메시지 길이 제한**: 사용자 입력 300자, 히스토리 200자
3. **응답 길이 제한**: max_tokens 300으로 설정
4. **캐싱 시스템**: 중복 API 호출 방지
5. **모델 선택**: gpt-3.5-turbo (비용 효율적)

### 프롬프트 엔지니어링
- `prompt.text` 파일에서 AI 성격 조정
- 공감 → 질문 → 정리 구조 유지
- 한국어 자연스러운 대화 스타일

## 🔒 보안 고려사항

### API 키 보안
- `.env` 파일을 `.gitignore`에 추가
- Git 히스토리에서 API 키 완전 제거
- Vercel 환경 변수 사용

### 데이터 보호
- 사용자 개인정보 암호화
- Supabase RLS 정책 설정
- 정기적인 보안 감사

## 📈 성능 모니터링

### 주요 지표
- 웹훅 응답 시간
- AI API 호출 성공률
- 데이터베이스 쿼리 성능
- 에러 발생 빈도

### 최적화 포인트
- 비동기 처리로 타임아웃 방지
- 캐싱으로 중복 요청 최소화
- 데이터베이스 인덱스 최적화

## 🚧 개발 가이드라인

### 코드 스타일
- ES6+ 문법 사용
- async/await 패턴 활용
- 에러 처리 및 로깅 철저히
- 주석으로 복잡한 로직 설명

### 테스트 전략
- 단위 테스트: 각 함수별 동작 검증
- 통합 테스트: 웹훅 엔드포인트 검증
- 로드 테스트: 동시 사용자 처리 능력

## 🔄 업데이트 및 유지보수

### 정기 업데이트
- 의존성 패키지 보안 업데이트
- OpenAI API 모델 업그레이드
- 카카오톡 API 변경사항 반영

### 백업 및 복구
- 데이터베이스 정기 백업
- 코드 버전 관리 (Git)
- 롤백 전략 수립

## 📞 지원 및 문의

### 개발팀 연락처
- **기술 문의**: [이메일 또는 연락처]
- **버그 리포트**: GitHub Issues
- **기능 요청**: GitHub Discussions

### 유용한 링크
- [Supabase 문서](https://supabase.com/docs)
- [OpenAI API 문서](https://platform.openai.com/docs)
- [카카오톡 봇 API 문서](https://developers.kakao.com/docs/latest/ko/kakaotalk-bot)


**질문이나 문제가 있으시면 언제든지 문의해주세요!** 🚀
