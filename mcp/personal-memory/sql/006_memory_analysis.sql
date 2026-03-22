ALTER TABLE conversation_event
    ADD COLUMN IF NOT EXISTS analyzed_status VARCHAR(32) NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS analyzed_at TIMESTAMPTZ NULL;

CREATE TABLE IF NOT EXISTS memory_analysis_result (
    id BIGSERIAL PRIMARY KEY,
    user_code VARCHAR(64) NOT NULL,
    session_key VARCHAR(128) NOT NULL,
    source_event_id BIGINT NULL REFERENCES conversation_event(id) ON DELETE SET NULL,
    category VARCHAR(64) NOT NULL,
    subject VARCHAR(128) NOT NULL,
    claim TEXT NOT NULL,
    rationale TEXT NOT NULL,
    evidence_type VARCHAR(32) NOT NULL,
    time_scope VARCHAR(32) NOT NULL,
    action VARCHAR(32) NOT NULL,
    confidence NUMERIC(4, 3) NOT NULL DEFAULT 0.500,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_memory_analysis_result_user_session_created
    ON memory_analysis_result (user_code, session_key, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_analysis_result_user_action_status
    ON memory_analysis_result (user_code, action, status, updated_at DESC);
