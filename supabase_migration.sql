-- ============================================
-- 3분 커리어 챗봇 - Supabase 마이그레이션
-- ============================================

-- ============================================
-- 1. users 테이블 (사용자 프로필)
-- ============================================
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    kakao_user_id TEXT UNIQUE NOT NULL,

    -- 온보딩 필드 (9개)
    name VARCHAR(100),
    job_title VARCHAR(200),
    total_years VARCHAR(50),
    job_years VARCHAR(50),
    career_goal TEXT,
    project_name TEXT,
    recent_work TEXT,
    job_meaning TEXT,
    important_thing TEXT,

    -- 카운터
    daily_record_count INTEGER DEFAULT 0,
    last_record_date DATE,

    -- 타임스탬프
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON TABLE users IS '사용자 프로필 및 온보딩 정보';
COMMENT ON COLUMN users.daily_record_count IS '일일 기록 횟수 (7일마다 리셋)';
COMMENT ON COLUMN users.last_record_date IS '마지막 기록 날짜';

-- ============================================
-- 2. conversation_states 테이블 (대화 상태)
-- ============================================
CREATE TABLE IF NOT EXISTS conversation_states (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    kakao_user_id TEXT UNIQUE NOT NULL,
    current_step TEXT,
    temp_data JSONB DEFAULT '{}'::jsonb,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT fk_state_user
        FOREIGN KEY (kakao_user_id)
        REFERENCES users(kakao_user_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_conversation_states_user
ON conversation_states(kakao_user_id);

COMMENT ON TABLE conversation_states IS '대화 상태 및 임시 데이터';
COMMENT ON COLUMN conversation_states.current_step IS '현재 대화 단계 (onboarding, daily_recording, weekly_summary_pending 등)';
COMMENT ON COLUMN conversation_states.temp_data IS '임시 데이터 (field_attempts, field_status, daily_session_data, weekly_summary_ready 등)';

-- temp_data 구조 예시:
-- {
--   "field_attempts": {"name": 1, "job_title": 2},
--   "field_status": {"name": "filled", "job_title": "filled"},
--   "daily_session_data": {"conversation_count": 3},
--   "weekly_summary_ready": true,
--   "daily_count": 7
-- }

-- ============================================
-- 3. ai_conversations 테이블 (대화 히스토리)
-- ============================================
CREATE TABLE IF NOT EXISTS ai_conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    kakao_user_id TEXT UNIQUE NOT NULL,
    conversation_history JSONB DEFAULT '[]'::jsonb,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT fk_conversations_user
        FOREIGN KEY (kakao_user_id)
        REFERENCES users(kakao_user_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ai_conversations_user
ON ai_conversations(kakao_user_id);

COMMENT ON TABLE ai_conversations IS '대화 히스토리 (JSONB 배열)';
COMMENT ON COLUMN ai_conversations.conversation_history IS '대화 배열 [{"role": "user", "content": "...", "created_at": "..."}]';

-- conversation_history 구조 예시:
-- [
--   {"role": "user", "content": "안녕", "created_at": "2025-10-13T12:00:00Z"},
--   {"role": "assistant", "content": "반갑습니다", "created_at": "2025-10-13T12:00:01Z"}
-- ]

-- ============================================
-- 4. daily_records 테이블 (일일 요약)
-- ============================================
CREATE TABLE IF NOT EXISTS daily_records (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    work_content TEXT NOT NULL,
    record_date DATE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT fk_daily_records_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE,

    -- 같은 날짜는 하나의 요약만 (upsert 지원)
    CONSTRAINT daily_records_user_id_record_date_key
        UNIQUE (user_id, record_date)
);

CREATE INDEX IF NOT EXISTS idx_daily_records_user_date
ON daily_records(user_id, record_date DESC);

COMMENT ON TABLE daily_records IS '일일 요약 저장 (같은 날짜는 최신 내용으로 업데이트)';
COMMENT ON COLUMN daily_records.work_content IS '일일 요약 내용';
COMMENT ON COLUMN daily_records.record_date IS '기록 날짜 (YYYY-MM-DD)';

-- ============================================
-- 5. weekly_summaries 테이블 (주간 요약)
-- ============================================
CREATE TABLE IF NOT EXISTS weekly_summaries (
    id BIGSERIAL PRIMARY KEY,
    kakao_user_id TEXT NOT NULL,
    sequence_number INTEGER NOT NULL,
    start_daily_count INTEGER NOT NULL,
    end_daily_count INTEGER NOT NULL,
    summary_content TEXT NOT NULL,
    start_date DATE,
    end_date DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT fk_weekly_summaries_user
        FOREIGN KEY (kakao_user_id)
        REFERENCES users(kakao_user_id)
        ON DELETE CASCADE,

    -- 같은 시퀀스 번호는 하나만 (upsert 지원)
    CONSTRAINT weekly_summaries_user_sequence_key
        UNIQUE (kakao_user_id, sequence_number)
);

CREATE INDEX IF NOT EXISTS idx_weekly_summaries_user
ON weekly_summaries(kakao_user_id, sequence_number DESC);

COMMENT ON TABLE weekly_summaries IS '주간 요약 저장 (7일차마다 생성)';
COMMENT ON COLUMN weekly_summaries.sequence_number IS '몇 번째 주차 (1, 2, 3, ...)';
COMMENT ON COLUMN weekly_summaries.start_daily_count IS '시작 일일기록 번호 (1, 8, 15, ...)';
COMMENT ON COLUMN weekly_summaries.end_daily_count IS '종료 일일기록 번호 (7, 14, 21, ...)';

-- ============================================
-- 6. Row Level Security (RLS) 설정 (선택)
-- ============================================
-- Supabase에서 보안 강화를 원한다면 활성화

-- ALTER TABLE users ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE conversation_states ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE ai_conversations ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE daily_records ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE weekly_summaries ENABLE ROW LEVEL SECURITY;

-- 예시: 사용자는 자신의 데이터만 조회 가능
-- CREATE POLICY "Users can view their own data"
-- ON users FOR SELECT
-- USING (kakao_user_id = current_setting('request.jwt.claim.user_id', true));

-- ============================================
