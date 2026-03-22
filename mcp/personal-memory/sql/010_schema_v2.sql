CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS memory_record (
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
    supersedes_id BIGINT NULL REFERENCES memory_record(id),
    conflict_with_id BIGINT NULL REFERENCES memory_record(id),
    valid_from TIMESTAMPTZ NULL,
    valid_to TIMESTAMPTZ NULL,
    subject_key VARCHAR(128) NULL,
    attribute_key VARCHAR(128) NULL,
    value_text TEXT NULL,
    conflict_scope VARCHAR(255) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ NULL,
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('simple', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(summary, '')), 'B') ||
        setweight(to_tsvector('simple', coalesce(content, '')), 'C')
    ) STORED
);

CREATE TABLE IF NOT EXISTS session_state (
    id BIGSERIAL PRIMARY KEY,
    user_code VARCHAR(64) NOT NULL,
    session_key VARCHAR(128) NOT NULL,
    memory_key VARCHAR(128) NULL,
    summary TEXT NOT NULL,
    source_text TEXT NULL,
    importance INT NOT NULL DEFAULT 3,
    expires_at TIMESTAMPTZ NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS memory_vector_chunk (
    id BIGSERIAL PRIMARY KEY,
    memory_id BIGINT NOT NULL REFERENCES memory_record(id) ON DELETE CASCADE,
    user_code VARCHAR(64) NOT NULL,
    chunk_index INT NOT NULL DEFAULT 0,
    chunk_text TEXT NOT NULL,
    embedding_text_hash VARCHAR(64) NULL,
    embedding vector(1536) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (memory_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS memory_candidate (
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

CREATE TABLE IF NOT EXISTS conversation_turn (
    id BIGSERIAL PRIMARY KEY,
    user_code VARCHAR(64) NOT NULL,
    session_key VARCHAR(128) NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    role VARCHAR(32) NOT NULL,
    content TEXT NOT NULL,
    source_ref VARCHAR(255) NULL,
    analyzed_status VARCHAR(32) NOT NULL DEFAULT 'pending',
    analyzed_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS memory_inference (
    id BIGSERIAL PRIMARY KEY,
    user_code VARCHAR(64) NOT NULL,
    session_key VARCHAR(128) NOT NULL,
    source_event_id BIGINT NULL REFERENCES conversation_turn(id) ON DELETE SET NULL,
    category VARCHAR(64) NOT NULL,
    subject VARCHAR(128) NOT NULL,
    attribute VARCHAR(128) NULL,
    value TEXT NULL,
    claim TEXT NOT NULL,
    rationale TEXT NOT NULL,
    evidence_type VARCHAR(32) NOT NULL,
    time_scope VARCHAR(32) NOT NULL,
    action VARCHAR(32) NOT NULL,
    confidence NUMERIC(4, 3) NOT NULL DEFAULT 0.500,
    conflict_scope VARCHAR(255) NULL,
    conflict_mode VARCHAR(32) NOT NULL DEFAULT 'coexist',
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS memory_signal (
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
    promoted_memory_id BIGINT NULL REFERENCES memory_record(id),
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_code, subject_key, attribute_key, value_text, status)
);

CREATE TABLE IF NOT EXISTS conversation_summary (
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
    parent_snapshot_id BIGINT NULL REFERENCES conversation_summary(id) ON DELETE SET NULL,
    turn_count INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ NULL,
    ended_at TIMESTAMPTZ NULL,
    source_ref VARCHAR(255) NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'memory_item'
    ) THEN
        INSERT INTO memory_record (
            id, user_code, memory_type, title, content, summary, tags,
            source_type, source_ref, confidence, importance, status,
            is_explicit, supersedes_id, conflict_with_id, valid_from, valid_to,
            subject_key, attribute_key, value_text, conflict_scope,
            created_at, updated_at, deleted_at
        )
        SELECT
            id, user_code, memory_type, title, content, summary, tags,
            source_type, source_ref, confidence, importance, status,
            is_explicit, supersedes_id, conflict_with_id, valid_from, valid_to,
            subject_key, attribute_key, value_text, conflict_scope,
            created_at, updated_at, deleted_at
        FROM memory_item
        ON CONFLICT (id) DO NOTHING;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'working_memory'
    ) THEN
        INSERT INTO session_state (
            id, user_code, session_key, memory_key, summary, source_text,
            importance, expires_at, status, created_at, updated_at
        )
        SELECT
            id, user_code, session_key, memory_key, summary, source_text,
            importance, expires_at, status, created_at, updated_at
        FROM working_memory
        ON CONFLICT (id) DO NOTHING;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'memory_embedding'
    ) THEN
        INSERT INTO memory_vector_chunk (
            id, memory_id, user_code, chunk_index, chunk_text, embedding_text_hash, embedding, created_at
        )
        SELECT
            id, memory_id, user_code, chunk_index, chunk_text, embedding_text_hash, embedding, created_at
        FROM memory_embedding
        ON CONFLICT (id) DO NOTHING;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'memory_review_candidate'
    ) THEN
        INSERT INTO memory_candidate (
            id, user_code, source_text, title, content, memory_type, reason,
            confidence, status, tags, created_at, updated_at
        )
        SELECT
            id, user_code, source_text, title, content, memory_type, reason,
            confidence, status, tags, created_at, updated_at
        FROM memory_review_candidate
        ON CONFLICT (id) DO NOTHING;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'conversation_event'
    ) THEN
        INSERT INTO conversation_turn (
            id, user_code, session_key, event_type, role, content,
            source_ref, analyzed_status, analyzed_at, created_at
        )
        SELECT
            id, user_code, session_key, event_type, role, content,
            source_ref, analyzed_status, analyzed_at, created_at
        FROM conversation_event
        ON CONFLICT (id) DO NOTHING;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'memory_analysis_result'
    ) THEN
        INSERT INTO memory_inference (
            id, user_code, session_key, source_event_id, category, subject, attribute, value,
            claim, rationale, evidence_type, time_scope, action, confidence,
            conflict_scope, conflict_mode, status, tags, created_at, updated_at
        )
        SELECT
            id, user_code, session_key, source_event_id, category, subject, attribute, value,
            claim, rationale, evidence_type, time_scope, action, confidence,
            conflict_scope, conflict_mode, status, tags, created_at, updated_at
        FROM memory_analysis_result
        ON CONFLICT (id) DO NOTHING;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'memory_evidence'
    ) THEN
        INSERT INTO memory_signal (
            id, user_code, category, subject_key, attribute_key, value_text, latest_claim,
            conflict_scope, evidence_type, time_scope, support_score, occurrence_count,
            promoted_memory_id, status, tags, first_seen_at, last_seen_at, created_at, updated_at
        )
        SELECT
            id, user_code, category, subject_key, attribute_key, value_text, latest_claim,
            conflict_scope, evidence_type, time_scope, support_score, occurrence_count,
            promoted_memory_id, status, tags, first_seen_at, last_seen_at, created_at, updated_at
        FROM memory_evidence
        ON CONFLICT (id) DO NOTHING;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'conversation_context_snapshot'
    ) THEN
        INSERT INTO conversation_summary (
            id, user_code, session_key, snapshot_level, topic_key, topic, summary,
            user_view, assistant_view, key_points, open_questions, source_event_ids,
            parent_snapshot_id, turn_count, started_at, ended_at, source_ref,
            status, created_at, updated_at
        )
        SELECT
            id, user_code, session_key, snapshot_level, topic_key, topic, summary,
            user_view, assistant_view, key_points, open_questions, source_event_ids,
            parent_snapshot_id, turn_count, started_at, ended_at, source_ref,
            status, created_at, updated_at
        FROM conversation_context_snapshot
        ON CONFLICT (id) DO NOTHING;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_memory_record_user_updated
    ON memory_record (user_code, updated_at DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_memory_record_user_subject_attribute
    ON memory_record (user_code, subject_key, attribute_key, updated_at DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_memory_record_user_conflict_scope
    ON memory_record (user_code, conflict_scope, updated_at DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_memory_vector_chunk_vector_cosine
    ON memory_vector_chunk
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_session_state_user_key_status
    ON session_state (user_code, memory_key, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_conversation_turn_user_session_created
    ON conversation_turn (user_code, session_key, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_inference_user_session_created
    ON memory_inference (user_code, session_key, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_inference_user_action_status
    ON memory_inference (user_code, action, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_signal_user_scope
    ON memory_signal (user_code, conflict_scope, last_seen_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_signal_user_attribute
    ON memory_signal (user_code, subject_key, attribute_key, last_seen_at DESC);

CREATE INDEX IF NOT EXISTS idx_conversation_summary_user_session_level
    ON conversation_summary (user_code, session_key, snapshot_level, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_conversation_summary_user_topic
    ON conversation_summary (user_code, topic_key, snapshot_level, updated_at DESC);

SELECT setval(pg_get_serial_sequence('memory_record', 'id'), COALESCE((SELECT max(id) FROM memory_record), 1), true);
SELECT setval(pg_get_serial_sequence('session_state', 'id'), COALESCE((SELECT max(id) FROM session_state), 1), true);
SELECT setval(pg_get_serial_sequence('memory_vector_chunk', 'id'), COALESCE((SELECT max(id) FROM memory_vector_chunk), 1), true);
SELECT setval(pg_get_serial_sequence('memory_candidate', 'id'), COALESCE((SELECT max(id) FROM memory_candidate), 1), true);
SELECT setval(pg_get_serial_sequence('conversation_turn', 'id'), COALESCE((SELECT max(id) FROM conversation_turn), 1), true);
SELECT setval(pg_get_serial_sequence('memory_inference', 'id'), COALESCE((SELECT max(id) FROM memory_inference), 1), true);
SELECT setval(pg_get_serial_sequence('memory_signal', 'id'), COALESCE((SELECT max(id) FROM memory_signal), 1), true);
SELECT setval(pg_get_serial_sequence('conversation_summary', 'id'), COALESCE((SELECT max(id) FROM conversation_summary), 1), true);
