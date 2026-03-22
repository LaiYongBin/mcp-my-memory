CREATE TABLE IF NOT EXISTS conversation_context_snapshot (
    id BIGSERIAL PRIMARY KEY,
    user_code VARCHAR(64) NOT NULL,
    session_key VARCHAR(128) NOT NULL,
    snapshot_level VARCHAR(32) NOT NULL,
    topic_key VARCHAR(128) NOT NULL,
    topic TEXT NOT NULL,
    summary TEXT NOT NULL,
    user_view TEXT NULL,
    assistant_view TEXT NULL,
    key_points JSONB NOT NULL DEFAULT '[]'::jsonb,
    open_questions JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_event_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    parent_snapshot_id BIGINT NULL REFERENCES conversation_context_snapshot(id) ON DELETE SET NULL,
    turn_count INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ NULL,
    ended_at TIMESTAMPTZ NULL,
    source_ref VARCHAR(255) NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_context_snapshot_user_session_level
    ON conversation_context_snapshot (user_code, session_key, snapshot_level, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_context_snapshot_user_topic
    ON conversation_context_snapshot (user_code, topic_key, snapshot_level, updated_at DESC);
