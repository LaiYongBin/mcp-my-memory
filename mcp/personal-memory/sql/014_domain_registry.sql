CREATE TABLE IF NOT EXISTS domain_registry (
    domain_name VARCHAR(64) PRIMARY KEY,
    domain_kind VARCHAR(32) NOT NULL,
    governance_mode VARCHAR(32) NOT NULL,
    default_value_key VARCHAR(64) NULL,
    description TEXT NULL,
    is_system BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS domain_value (
    id BIGSERIAL PRIMARY KEY,
    domain_name VARCHAR(64) NOT NULL REFERENCES domain_registry(domain_name) ON DELETE CASCADE,
    value_key VARCHAR(64) NOT NULL,
    display_name VARCHAR(128) NOT NULL,
    description TEXT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    is_builtin BOOLEAN NOT NULL DEFAULT FALSE,
    created_by VARCHAR(64) NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (domain_name, value_key)
);

CREATE TABLE IF NOT EXISTS domain_value_alias (
    id BIGSERIAL PRIMARY KEY,
    domain_name VARCHAR(64) NOT NULL,
    alias_key VARCHAR(64) NOT NULL,
    canonical_value_key VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (domain_name, alias_key),
    FOREIGN KEY (domain_name) REFERENCES domain_registry(domain_name) ON DELETE CASCADE,
    FOREIGN KEY (domain_name, canonical_value_key) REFERENCES domain_value(domain_name, value_key) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS domain_value_candidate (
    id BIGSERIAL PRIMARY KEY,
    domain_name VARCHAR(64) NOT NULL REFERENCES domain_registry(domain_name) ON DELETE CASCADE,
    proposed_value_key VARCHAR(128) NOT NULL,
    normalized_value_key VARCHAR(64) NOT NULL,
    canonical_value_key VARCHAR(64) NULL,
    source VARCHAR(64) NOT NULL,
    source_ref VARCHAR(255) NULL,
    reason TEXT NULL,
    confidence NUMERIC(4, 3) NOT NULL DEFAULT 0.600,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    created_by VARCHAR(64) NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (domain_name, normalized_value_key, status)
);

INSERT INTO domain_registry (domain_name, domain_kind, governance_mode, default_value_key, description, is_system)
VALUES
    ('memory_type', 'taxonomy', 'manual_review', 'fact', 'Expandable memory classification taxonomy', TRUE),
    ('source_type', 'taxonomy', 'manual_review', 'manual', 'Governed source classification taxonomy', TRUE),
    ('action', 'execution_enum', 'fixed', NULL, 'Fixed execution semantics for inference routing', TRUE),
    ('snapshot_level', 'execution_enum', 'fixed', NULL, 'Fixed context summarization levels', TRUE)
ON CONFLICT (domain_name) DO UPDATE
SET domain_kind = EXCLUDED.domain_kind,
    governance_mode = EXCLUDED.governance_mode,
    default_value_key = EXCLUDED.default_value_key,
    description = EXCLUDED.description,
    updated_at = now();

INSERT INTO domain_value (
    domain_name, value_key, display_name, description, status, is_builtin, created_by
)
VALUES
    ('memory_type', 'fact', 'fact', 'General factual memory', 'active', TRUE, 'system'),
    ('memory_type', 'preference', 'preference', 'Stable user preference', 'active', TRUE, 'system'),
    ('memory_type', 'context', 'context', 'Context-derived long-term memory', 'active', TRUE, 'system'),
    ('memory_type', 'relationship', 'relationship', 'Relationship-related memory', 'active', TRUE, 'system'),
    ('memory_type', 'rule', 'rule', 'Collaboration or behavior rule', 'active', TRUE, 'system'),
    ('source_type', 'manual', 'manual', 'Explicit manual memory write', 'active', TRUE, 'system'),
    ('source_type', 'conversation', 'conversation', 'Captured from conversation', 'active', TRUE, 'system'),
    ('source_type', 'review-approved', 'review-approved', 'Approved from review queue', 'active', TRUE, 'system'),
    ('source_type', 'consolidation', 'consolidation', 'Created during working-memory consolidation', 'active', TRUE, 'system'),
    ('source_type', 'analysis', 'analysis', 'Created from analyzer output', 'active', TRUE, 'system'),
    ('action', 'long_term', 'long_term', 'Persist as durable memory', 'active', TRUE, 'system'),
    ('action', 'working_memory', 'working_memory', 'Persist as short-lived session state', 'active', TRUE, 'system'),
    ('action', 'review', 'review', 'Send to review queue', 'active', TRUE, 'system'),
    ('action', 'ignore', 'ignore', 'Do not persist', 'active', TRUE, 'system'),
    ('snapshot_level', 'segment', 'segment', 'Single segment summary', 'active', TRUE, 'system'),
    ('snapshot_level', 'topic', 'topic', 'Session-topic summary', 'active', TRUE, 'system'),
    ('snapshot_level', 'global_topic', 'global_topic', 'Cross-session topic summary', 'active', TRUE, 'system')
ON CONFLICT (domain_name, value_key) DO UPDATE
SET display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    status = EXCLUDED.status,
    updated_at = now();

INSERT INTO domain_value_alias (domain_name, alias_key, canonical_value_key)
VALUES
    ('source_type', 'review_approved', 'review-approved'),
    ('source_type', 'reviewapproved', 'review-approved')
ON CONFLICT (domain_name, alias_key) DO UPDATE
SET canonical_value_key = EXCLUDED.canonical_value_key;

CREATE INDEX IF NOT EXISTS idx_domain_value_domain_status
    ON domain_value (domain_name, status, value_key);

CREATE INDEX IF NOT EXISTS idx_domain_candidate_status_updated
    ON domain_value_candidate (status, updated_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_domain_candidate_domain_status
    ON domain_value_candidate (domain_name, status, updated_at DESC);
