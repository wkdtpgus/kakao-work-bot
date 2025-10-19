-- ============================================
-- 3분 커리어 챗봇 - 개선된 대화 히스토리 스키마 V2
-- ============================================
-- 설계 원칙:
-- 1. UUID 키값으로 보안 강화
-- 2. 테이블 분리로 속도 개선
-- 3. 턴 단위 대화 관리
-- 4. 뷰 기반 실시간 조회 (최근 5개 턴)
-- ============================================
--
-- 📊 최종 구조 (2025-10-19 업데이트):
--
-- 테이블 (물리적 저장):
-- 1. user_answer_messages     - 유저 메시지
-- 2. ai_answer_messages        - AI 응답 (is_summary, summary_type 필드 포함)
-- 3. message_history           - 대화 턴 히스토리
--
-- 뷰 (실시간 조회):
-- 4. recent_conversations      - 최근 5개 턴 (뷰)
-- 5. summary_messages_view     - 요약 메시지만 조회 (뷰)
--
-- 함수 (RPC):
-- - get_recent_turns()                           - 최근 N개 턴 조회
-- - get_turns_by_date()                          - 특정 날짜의 대화 턴 조회
-- - get_recent_daily_summaries_by_unique_dates() - 고유 날짜별 데일리 요약 조회
--
-- 삭제된 구조 (더 이상 사용 안 함):
-- ❌ user_answer_count (테이블)
-- ❌ ai_answer_count (테이블)
-- ❌ conversation_history_view (뷰)
-- ❌ recent_conversations (테이블 → 뷰로 변경)
-- ❌ update_recent_conversations() (트리거 함수)
-- ❌ daily_records (테이블) - ai_answer_messages로 통합
-- ❌ weekly_summaries (테이블) - ai_answer_messages로 통합
-- ❌ link_messages_to_daily_record_v2 (트리거)
-- ❌ daily_conversation_stats (뷰) - 사용되지 않아 제거
-- ============================================

-- ============================================
-- 1. user_answer_messages 테이블 (유저 메시지)
-- ============================================
CREATE TABLE IF NOT EXISTS user_answer_messages (
    id BIGSERIAL PRIMARY KEY,
    uuid UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
    kakao_user_id TEXT NOT NULL,

    -- 메시지 내용
    content TEXT NOT NULL,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT fk_user_answer_user
        FOREIGN KEY (kakao_user_id)
        REFERENCES users(kakao_user_id)
        ON DELETE CASCADE
);

CREATE INDEX idx_user_answer_uuid
ON user_answer_messages(uuid);

CREATE INDEX idx_user_answer_user
ON user_answer_messages(kakao_user_id, created_at DESC);

COMMENT ON TABLE user_answer_messages IS '사용자 메시지 저장';
COMMENT ON COLUMN user_answer_messages.uuid IS 'message_history에서 참조하는 고유 키';

-- ============================================
-- 2. ai_answer_messages 테이블 (AI 응답 메시지)
-- ============================================
CREATE TABLE IF NOT EXISTS ai_answer_messages (
    id BIGSERIAL PRIMARY KEY,
    uuid UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
    kakao_user_id TEXT NOT NULL,

    -- 메시지 내용
    content TEXT NOT NULL,

    -- 요약 여부 (0: 일반 응답, 1: 데일리/위클리 요약)
    is_summary BOOLEAN DEFAULT FALSE,

    -- 요약 타입 (NULL: 일반 대화, 'daily': 일일 요약, 'weekly': 주간 요약)
    summary_type VARCHAR(20),

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT fk_ai_answer_user
        FOREIGN KEY (kakao_user_id)
        REFERENCES users(kakao_user_id)
        ON DELETE CASCADE
);

CREATE INDEX idx_ai_answer_uuid
ON ai_answer_messages(uuid);

CREATE INDEX idx_ai_answer_user
ON ai_answer_messages(kakao_user_id, created_at DESC);

CREATE INDEX idx_ai_answer_summary
ON ai_answer_messages(kakao_user_id, is_summary) WHERE is_summary = TRUE;

CREATE INDEX idx_ai_answer_summary_type
ON ai_answer_messages(kakao_user_id, summary_type) WHERE summary_type IS NOT NULL;

COMMENT ON TABLE ai_answer_messages IS 'AI 응답 메시지 저장';
COMMENT ON COLUMN ai_answer_messages.uuid IS 'message_history에서 참조하는 고유 키';
COMMENT ON COLUMN ai_answer_messages.is_summary IS '요약 메시지 여부 (FALSE: 일반 응답, TRUE: 데일리/위클리 요약)';
COMMENT ON COLUMN ai_answer_messages.summary_type IS '요약 타입: daily(일일 요약), weekly(주간 요약), NULL(일반 대화)';

-- ============================================
-- 3. message_history 테이블 (대화 턴 히스토리)
-- ============================================
CREATE TABLE IF NOT EXISTS message_history (
    id BIGSERIAL PRIMARY KEY,
    uuid UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
    kakao_user_id TEXT NOT NULL,

    -- 대화 턴 참조 (UUID 키값)
    user_answer_key UUID NOT NULL,
    ai_answer_key UUID NOT NULL,

    -- 메타데이터
    session_date DATE NOT NULL,
    turn_index INTEGER,  -- 날짜 내 턴 순서

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

CREATE INDEX idx_message_history_user_date
ON message_history(kakao_user_id, session_date DESC, turn_index DESC);

CREATE INDEX idx_message_history_uuid
ON message_history(uuid);

COMMENT ON TABLE message_history IS '대화 턴 히스토리 (user-ai 쌍 관리, UUID 키로 참조)';
COMMENT ON COLUMN message_history.user_answer_key IS 'user_answer_messages 테이블의 UUID';
COMMENT ON COLUMN message_history.ai_answer_key IS 'ai_answer_messages 테이블의 UUID';

-- ============================================
-- 4. recent_conversations 뷰 (숏텀 메모리)
-- ============================================
-- 최근 5개 턴을 실시간 조회하는 뷰
CREATE OR REPLACE VIEW recent_conversations AS
WITH ranked_messages AS (
    SELECT
        mh.kakao_user_id,
        um.content as user_message,
        am.content as ai_message,
        mh.created_at,
        ROW_NUMBER() OVER (PARTITION BY mh.kakao_user_id ORDER BY mh.created_at DESC) as rn
    FROM message_history mh
    JOIN user_answer_messages um ON mh.user_answer_key = um.uuid
    JOIN ai_answer_messages am ON mh.ai_answer_key = am.uuid
)
SELECT
    kakao_user_id,
    jsonb_agg(
        jsonb_build_object('user', user_message, 'ai', ai_message)
        ORDER BY created_at DESC
    ) as recent_turns
FROM ranked_messages
WHERE rn <= 5
GROUP BY kakao_user_id;

COMMENT ON VIEW recent_conversations IS '최근 5개 턴을 실시간 조회하는 뷰 (물리적 저장 없음, 항상 최신 데이터)';

-- ============================================
-- 5. 편의 함수들
-- ============================================

-- 5-1. 최근 N개 턴 조회 (message_history 기반)
CREATE OR REPLACE FUNCTION get_recent_turns(
    p_kakao_user_id TEXT,
    p_limit INTEGER DEFAULT 5
)
RETURNS TABLE (
    turn_index INTEGER,
    user_message TEXT,
    ai_message TEXT,
    session_date DATE,
    created_at TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        mh.turn_index,
        um.content as user_message,
        am.content as ai_message,
        mh.session_date,
        mh.created_at
    FROM message_history mh
    JOIN user_answer_messages um ON mh.user_answer_key = um.uuid
    JOIN ai_answer_messages am ON mh.ai_answer_key = am.uuid
    WHERE mh.kakao_user_id = p_kakao_user_id
    ORDER BY mh.created_at DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_recent_turns(TEXT, INTEGER)
IS '최근 N개 턴 조회 (user-ai 쌍으로 반환)';

-- 5-2. 특정 날짜의 대화 턴 조회
CREATE OR REPLACE FUNCTION get_turns_by_date(
    p_kakao_user_id TEXT,
    p_session_date DATE
)
RETURNS TABLE (
    turn_index INTEGER,
    user_message TEXT,
    ai_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        mh.turn_index,
        um.content as user_message,
        am.content as ai_message,
        mh.created_at
    FROM message_history mh
    JOIN user_answer_messages um ON mh.user_answer_key = um.uuid
    JOIN ai_answer_messages am ON mh.ai_answer_key = am.uuid
    WHERE mh.kakao_user_id = p_kakao_user_id
      AND mh.session_date = p_session_date
    ORDER BY mh.turn_index ASC;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_turns_by_date(TEXT, DATE)
IS '특정 날짜의 대화 턴 조회';

-- ============================================
-- 6. 유용한 뷰 (View)
-- ============================================

-- 6-1. 요약 메시지만 조회하는 뷰
CREATE OR REPLACE VIEW summary_messages_view AS
SELECT
    am.id,
    am.uuid,
    am.kakao_user_id,
    am.content as summary_content,
    am.is_summary,
    am.summary_type,  -- 🆕 추가: daily/weekly 구분
    am.created_at,
    mh.session_date,
    mh.turn_index,
    um.content as user_request
FROM ai_answer_messages am
LEFT JOIN message_history mh ON mh.ai_answer_key = am.uuid
LEFT JOIN user_answer_messages um ON mh.user_answer_key = um.uuid
WHERE am.is_summary = TRUE
ORDER BY am.created_at DESC;

COMMENT ON VIEW summary_messages_view
IS '데일리/위클리 요약 메시지만 조회 (is_summary = TRUE, summary_type으로 구분)';

-- ============================================
-- 7. 요약 관련 특수 함수
-- ============================================

-- 7-1. 고유 날짜별 데일리 요약 조회 (하루에 여러 요약 생성 시 최신 것만 선택)
CREATE OR REPLACE FUNCTION get_recent_daily_summaries_by_unique_dates(
    p_kakao_user_id TEXT,
    p_limit INTEGER DEFAULT 7
)
RETURNS TABLE (
    id BIGINT,
    uuid UUID,
    kakao_user_id TEXT,
    summary_content TEXT,
    is_summary BOOLEAN,
    summary_type VARCHAR(20),
    created_at TIMESTAMP WITH TIME ZONE,
    session_date DATE,
    turn_index INTEGER,
    user_request TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT DISTINCT ON (smv.session_date)
        smv.id,
        smv.uuid,
        smv.kakao_user_id,
        smv.summary_content,
        smv.is_summary,
        smv.summary_type,
        smv.created_at,
        smv.session_date,
        smv.turn_index,
        smv.user_request
    FROM summary_messages_view smv
    WHERE smv.kakao_user_id = p_kakao_user_id
      AND smv.summary_type = 'daily'
    ORDER BY smv.session_date DESC, smv.created_at DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_recent_daily_summaries_by_unique_dates(TEXT, INTEGER)
IS '최근 N개의 고유 날짜별 데일리 요약 조회 (하루에 여러 요약 생성 시 최신 것만 반환)';

-- ============================================
-- 스키마 생성 완료!
-- ============================================
-- 다음 단계: 마이그레이션 함수는 별도 파일에서 실행
