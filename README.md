# Kakao Work Bot

카카오톡 챗봇을 통한 3분커리어 온보딩 및 AI Agent 대화 시스템

## 환경 변수 설정

1. `.env.example` 파일을 `.env`로 복사
2. 실제 API 키 값으로 수정

```bash
cp .env.example .env
# .env 파일을 편집하여 실제 값 입력
```

## 필요한 환경 변수

- `SUPABASE_URL`: Supabase 프로젝트 URL
- `SUPABASE_ANON_KEY`: Supabase 익명 키
- `OPENAI_API_KEY`: OpenAI API 키
- `PORT`: 서버 포트 (기본값: 3000)

## 보안 주의사항

⚠️ **절대 `.env` 파일을 Git에 커밋하지 마세요!**
- API 키가 노출되어 보안 위험이 있습니다
- `.env` 파일은 `.gitignore`에 포함되어 있습니다
- `.env.example`만 공유하여 필요한 환경 변수를 안내합니다
