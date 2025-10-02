-- ============================================
-- 카카오톡 챗봇 메모리 관리 테이블
-- ============================================

-- 1️⃣ conversations 테이블 (롱텀 메모리 - 대화 전문)
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- users 테이블과 연결 (사용자 삭제 시 대화도 삭제)
    CONSTRAINT fk_user
        FOREIGN KEY (user_id)
        REFERENCES users(kakao_user_id)
        ON DELETE CASCADE
);

-- 인덱스: 사용자별 최근 대화 조회 최적화
CREATE INDEX IF NOT EXISTS idx_conversations_user_created
ON conversations(user_id, created_at DESC);

-- 인덱스: 날짜별 조회 최적화
CREATE INDEX IF NOT EXISTS idx_conversations_created
ON conversations(created_at DESC);

COMMENT ON TABLE conversations IS '모든 대화 기록 (롱텀 메모리 - 영구 보관)';
COMMENT ON COLUMN conversations.user_id IS '카카오톡 사용자 ID';
COMMENT ON COLUMN conversations.role IS '발화자 (user: 사용자, assistant: AI)';
COMMENT ON COLUMN conversations.content IS '대화 내용';

-- ============================================

-- 2️⃣ conversation_summaries 테이블 (숏텀 메모리 - 요약)
CREATE TABLE IF NOT EXISTS conversation_summaries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL UNIQUE,
    summary TEXT NOT NULL,
    summarized_until INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- users 테이블과 연결
    CONSTRAINT fk_summary_user
        FOREIGN KEY (user_id)
        REFERENCES users(kakao_user_id)
        ON DELETE CASCADE
);

-- 인덱스: 사용자별 요약 조회
CREATE INDEX IF NOT EXISTS idx_summaries_user
ON conversation_summaries(user_id);

COMMENT ON TABLE conversation_summaries IS '대화 요약 (숏텀 메모리 - LLM 컨텍스트용)';
COMMENT ON COLUMN conversation_summaries.summary IS '대화 요약 텍스트';
COMMENT ON COLUMN conversation_summaries.summarized_until IS '몇 번째 메시지까지 요약했는지';

-- ============================================

-- 3️⃣ 기존 테이블 확인용 쿼리 (실행 후 확인)
-- SELECT table_name FROM information_schema.tables
-- WHERE table_schema = 'public'
-- AND table_name IN ('users', 'conversations', 'conversation_summaries', 'conversation_states');

-- ============================================

-- 3️⃣ conversation_states 테이블 (대화 상태 및 임시 데이터)
CREATE TABLE IF NOT EXISTS conversation_states (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    kakao_user_id TEXT NOT NULL UNIQUE,
    current_step TEXT,
    temp_data JSONB DEFAULT '{}'::jsonb,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- users 테이블과 연결
    CONSTRAINT fk_state_user
        FOREIGN KEY (kakao_user_id)
        REFERENCES users(kakao_user_id)
        ON DELETE CASCADE
);

-- 인덱스: 사용자별 상태 조회
CREATE INDEX IF NOT EXISTS idx_conversation_states_user
ON conversation_states(kakao_user_id);

COMMENT ON TABLE conversation_states IS '대화 상태 및 임시 데이터 (온보딩 진행 상태, field_attempts 등)';
COMMENT ON COLUMN conversation_states.current_step IS '현재 대화 단계 (onboarding, ai_intro, ai_conversation 등)';
COMMENT ON COLUMN conversation_states.temp_data IS '임시 데이터 (field_attempts, field_status 등 JSON)';

-- ============================================

-- 4️⃣ Row Level Security (RLS) 설정 (선택적)
-- Supabase에서 보안 강화를 원한다면 활성화

-- ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE conversation_summaries ENABLE ROW LEVEL SECURITY;

-- CREATE POLICY "Users can view their own conversations"
-- ON conversations FOR SELECT
-- USING (user_id = current_setting('request.jwt.claim.user_id', true));

-- CREATE POLICY "Users can view their own summaries"
-- ON conversation_summaries FOR SELECT
-- USING (user_id = current_setting('request.jwt.claim.user_id', true));

-- ============================================
