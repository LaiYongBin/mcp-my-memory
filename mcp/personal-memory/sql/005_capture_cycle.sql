ALTER TABLE working_memory
    ADD COLUMN IF NOT EXISTS memory_key VARCHAR(128) NULL,
    ADD COLUMN IF NOT EXISTS source_text TEXT NULL,
    ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'active';

CREATE TABLE IF NOT EXISTS conversation_event (
    id BIGSERIAL PRIMARY KEY,
    user_code VARCHAR(64) NOT NULL,
    session_key VARCHAR(128) NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    role VARCHAR(32) NOT NULL,
    content TEXT NOT NULL,
    source_ref VARCHAR(255) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conversation_event_user_session_created
    ON conversation_event (user_code, session_key, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_working_memory_user_key_status
    ON working_memory (user_code, memory_key, status, updated_at DESC);
