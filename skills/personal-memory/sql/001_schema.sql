CREATE TABLE IF NOT EXISTS memory_item (
    id BIGSERIAL PRIMARY KEY,
    user_code VARCHAR(64) NOT NULL,
    memory_type VARCHAR(32) NOT NULL,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    summary TEXT NULL,
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_type VARCHAR(32) NOT NULL DEFAULT 'manual',
    source_ref VARCHAR(255) NULL,
    confidence NUMERIC(4, 3) NOT NULL DEFAULT 0.700,
    importance INT NOT NULL DEFAULT 5,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    is_explicit BOOLEAN NOT NULL DEFAULT FALSE,
    supersedes_id BIGINT NULL REFERENCES memory_item(id),
    conflict_with_id BIGINT NULL REFERENCES memory_item(id),
    valid_from TIMESTAMPTZ NULL,
    valid_to TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ NULL,
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('simple', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(summary, '')), 'B') ||
        setweight(to_tsvector('simple', coalesce(content, '')), 'C')
    ) STORED
);

CREATE TABLE IF NOT EXISTS working_memory (
    id BIGSERIAL PRIMARY KEY,
    user_code VARCHAR(64) NOT NULL,
    session_key VARCHAR(128) NOT NULL,
    summary TEXT NOT NULL,
    importance INT NOT NULL DEFAULT 3,
    expires_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS memory_embedding (
    id BIGSERIAL PRIMARY KEY,
    memory_id BIGINT NOT NULL REFERENCES memory_item(id) ON DELETE CASCADE,
    user_code VARCHAR(64) NOT NULL,
    chunk_index INT NOT NULL DEFAULT 0,
    chunk_text TEXT NOT NULL,
    embedding_text_hash VARCHAR(64) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

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
