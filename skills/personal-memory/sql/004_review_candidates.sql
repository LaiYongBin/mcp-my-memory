CREATE TABLE IF NOT EXISTS memory_review_candidate (
    id BIGSERIAL PRIMARY KEY,
    user_code VARCHAR(64) NOT NULL,
    source_text TEXT NOT NULL,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    memory_type VARCHAR(32) NOT NULL,
    reason VARCHAR(255) NOT NULL,
    confidence NUMERIC(4, 3) NOT NULL DEFAULT 0.500,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_memory_review_candidate_user_status
    ON memory_review_candidate (user_code, status, updated_at DESC);
