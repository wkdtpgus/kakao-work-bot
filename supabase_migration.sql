-- ============================================
-- 3분 커리어 챗봇 - Supabase 마이그레이션
-- ============================================

-- UUID 확장 활성화
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- 1. users 테이블 (사용자 프로필)
-- ============================================
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    kakao_user_id VARCHAR UNIQUE NOT NULL,

    -- 온보딩 필드 (9개)
    name VARCHAR NOT NULL,
    job_title VARCHAR,
    total_years VARCHAR,
    job_years VARCHAR,
    career_goal TEXT,
    project_name TEXT,
    recent_work TEXT,
    job_meaning TEXT,
    important_thing TEXT,

    -- 온보딩 완료 여부
    onboarding_completed BOOLEAN DEFAULT FALSE,

    -- 카운터
    attendance_count INTEGER DEFAULT 0,
    daily_record_count INTEGER DEFAULT 0,
    last_record_date DATE,
    onboarding_completed_at TIMESTAMP WITH TIME ZONE,

    -- 타임스탬프
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON TABLE users IS '사용자 프로필 및 온보딩 정보';
COMMENT ON COLUMN users.onboarding_completed_at IS '온보딩 완료 시점 (당일 일일기록 차단용)';
COMMENT ON COLUMN users.attendance_count IS '평일(월~금) 출석 누적 카운트 (리셋 없이 계속 증가)';
COMMENT ON COLUMN users.daily_record_count IS '오늘의 대화 턴 수 (날짜 변경 시 0으로 리셋, 4회 달성 + 평일이면 attendance_count 증가)';
COMMENT ON COLUMN users.last_record_date IS '마지막 기록 날짜';

-- users 테이블 updated_at 자동 업데이트 트리거
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- 2. conversation_states 테이블 (대화 상태)
-- ============================================
CREATE TABLE IF NOT EXISTS conversation_states (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    kakao_user_id VARCHAR UNIQUE NOT NULL,
    current_step VARCHAR NOT NULL,
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
COMMENT ON COLUMN conversation_states.temp_data IS '임시 데이터 (field_attempts, field_status, daily_session_data, weekly_summary_ready, weekday_record_count, weekly_qna_session 등)';

-- temp_data 구조 예시:
-- {
--   "field_attempts": {"name": 1, "job_title": 2},
--   "field_status": {"name": "filled", "job_title": "filled"},
--   "daily_session_data": {"conversation_count": 3, "last_summary_at": "2025-01-10T15:30:00"},
--   "weekly_summary_ready": true,
--   "attendance_count": 7,
--   "weekday_record_count": 2,
--   "weekday_count_week": "2025-W02",
--   "last_weekday_record_date": "2025-01-10",
--   "weekly_completed_week": "2025-W02",
--   "weekly_qna_session": {
--     "active": true,
--     "v1_summary": "주간요약 v1.0 텍스트",
--     "follow_up_questions": ["질문1", "질문2", "질문3"],
--     "turn_count": 2,
--     "max_turns": 5,
--     "conversation_history": [{"user": "답변1", "ai": "질문1"}, ...]
--   }
-- }

-- ============================================
-- 3. user_answer_messages 테이블 (사용자 응답 메시지)
-- ============================================
CREATE TABLE IF NOT EXISTS user_answer_messages (
    uuid UUID PRIMARY KEY DEFAULT gen_random_uuid() UNIQUE,
    kakao_user_id TEXT NOT NULL,
    content TEXT NOT NULL,
    is_review BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT fk_user_answer_user
        FOREIGN KEY (kakao_user_id)
        REFERENCES users(kakao_user_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_user_answer_messages_user
ON user_answer_messages(kakao_user_id);

CREATE INDEX IF NOT EXISTS idx_user_answer_messages_review
ON user_answer_messages(kakao_user_id, is_review);

COMMENT ON TABLE user_answer_messages IS '사용자 응답 메시지';
COMMENT ON COLUMN user_answer_messages.is_review IS '주간 소감/리뷰 메시지 여부';

-- ============================================
-- 4. ai_answer_messages 테이블 (AI 응답 메시지)
-- ============================================
CREATE TABLE IF NOT EXISTS ai_answer_messages (
    uuid UUID PRIMARY KEY DEFAULT gen_random_uuid() UNIQUE,
    kakao_user_id TEXT NOT NULL,
    content TEXT NOT NULL,
    is_summary BOOLEAN DEFAULT FALSE,
    summary_type VARCHAR,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT fk_ai_answer_user
        FOREIGN KEY (kakao_user_id)
        REFERENCES users(kakao_user_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ai_answer_messages_user
ON ai_answer_messages(kakao_user_id);

COMMENT ON TABLE ai_answer_messages IS 'AI 응답 메시지';
COMMENT ON COLUMN ai_answer_messages.is_summary IS '요약 메시지 여부';
COMMENT ON COLUMN ai_answer_messages.summary_type IS '요약 유형 (daily, weekly_v1, weekly_v2)';

-- ============================================
-- 5. message_history 테이블 (메시지 히스토리)
-- ============================================
CREATE TABLE IF NOT EXISTS message_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid() UNIQUE,
    kakao_user_id TEXT NOT NULL,
    user_answer_key UUID NOT NULL,
    ai_answer_key UUID NOT NULL,
    session_date DATE NOT NULL,
    turn_index INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT fk_message_history_user
        FOREIGN KEY (kakao_user_id)
        REFERENCES users(kakao_user_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_message_history_user_answer
        FOREIGN KEY (user_answer_key)
        REFERENCES user_answer_messages(uuid)
        ON DELETE CASCADE,
    CONSTRAINT fk_message_history_ai_answer
        FOREIGN KEY (ai_answer_key)
        REFERENCES ai_answer_messages(uuid)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_message_history_user
ON message_history(kakao_user_id, session_date DESC);

CREATE INDEX IF NOT EXISTS idx_message_history_session
ON message_history(kakao_user_id, session_date, turn_index);

COMMENT ON TABLE message_history IS '메시지 히스토리 (턴 단위)';
COMMENT ON COLUMN message_history.session_date IS '세션 날짜';
COMMENT ON COLUMN message_history.turn_index IS '턴 인덱스 (세션 내 순서)';

-- ============================================
-- 6. daily_records 테이블 (일일 요약)
-- ============================================
CREATE TABLE IF NOT EXISTS daily_records (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,
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
-- 7. weekly_summaries 테이블 (주간 요약)
-- ============================================
CREATE TABLE IF NOT EXISTS weekly_summaries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    kakao_user_id VARCHAR NOT NULL,
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
-- 8. RPC 함수들
-- ============================================

-- 일일 요약 조회 함수 (이번 주 또는 지난 주 평일 요약만 반환)
-- 기존 함수가 있으면 삭제 후 재생성
DROP FUNCTION IF EXISTS get_recent_daily_summaries_by_unique_dates(TEXT, INT);

CREATE FUNCTION get_recent_daily_summaries_by_unique_dates(
    p_kakao_user_id TEXT,
    p_limit INT DEFAULT 7
)
RETURNS TABLE (
    summary_content TEXT,
    created_at TIMESTAMPTZ,
    summary_type VARCHAR
) AS $$
DECLARE
    v_week_start DATE;
    v_week_end DATE;
BEGIN
    -- 이번 주의 시작일(월요일)과 종료일(일요일) 계산
    v_week_start := DATE_TRUNC('week', CURRENT_DATE)::DATE;  -- 이번 주 월요일
    v_week_end := v_week_start + INTERVAL '6 days';          -- 이번 주 일요일

    -- 만약 오늘이 월요일이면 지난 주 데이터를 가져옴
    IF EXTRACT(DOW FROM CURRENT_DATE) = 1 THEN
        v_week_start := v_week_start - INTERVAL '7 days';
        v_week_end := v_week_end - INTERVAL '7 days';
    END IF;

    RETURN QUERY
    SELECT
        ai_answer_messages.content AS summary_content,
        ai_answer_messages.created_at,
        ai_answer_messages.summary_type
    FROM ai_answer_messages
    WHERE ai_answer_messages.kakao_user_id = p_kakao_user_id
      AND ai_answer_messages.is_summary = TRUE
      AND ai_answer_messages.summary_type = 'daily'
      AND DATE(ai_answer_messages.created_at) BETWEEN v_week_start AND v_week_end
      -- 평일(월~금)만 포함 (1=월, 5=금)
      AND EXTRACT(DOW FROM ai_answer_messages.created_at) BETWEEN 1 AND 5
    ORDER BY ai_answer_messages.created_at DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_recent_daily_summaries_by_unique_dates IS '이번 주 평일 일일 요약 조회 (월요일이면 지난 주)';

-- ============================================
-- 9. Row Level Security (RLS) 설정 (선택)
-- ============================================
-- Supabase에서 보안 강화를 원한다면 활성화

-- ALTER TABLE users ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE conversation_states ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE user_answer_messages ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE ai_answer_messages ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE message_history ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE daily_records ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE weekly_summaries ENABLE ROW LEVEL SECURITY;

-- 예시: 사용자는 자신의 데이터만 조회 가능
-- CREATE POLICY "Users can view their own data"
-- ON users FOR SELECT
-- USING (kakao_user_id = current_setting('request.jwt.claim.user_id', true));

-- ============================================
