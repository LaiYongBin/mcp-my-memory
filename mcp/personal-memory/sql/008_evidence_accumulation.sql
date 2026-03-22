CREATE TABLE IF NOT EXISTS memory_evidence (
    id BIGSERIAL PRIMARY KEY,
    user_code VARCHAR(64) NOT NULL,
    category VARCHAR(64) NOT NULL,
    subject_key VARCHAR(128) NOT NULL,
    attribute_key VARCHAR(128) NOT NULL,
    value_text TEXT NOT NULL,
    latest_claim TEXT NOT NULL,
    conflict_scope VARCHAR(255) NULL,
    evidence_type VARCHAR(32) NOT NULL,
    time_scope VARCHAR(32) NOT NULL,
    support_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    occurrence_count INTEGER NOT NULL DEFAULT 0,
    promoted_memory_id BIGINT NULL REFERENCES memory_item(id),
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_code, subject_key, attribute_key, value_text, status)
);

CREATE INDEX IF NOT EXISTS idx_memory_evidence_user_scope
    ON memory_evidence (user_code, conflict_scope, last_seen_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_evidence_user_attribute
    ON memory_evidence (user_code, subject_key, attribute_key, last_seen_at DESC);
