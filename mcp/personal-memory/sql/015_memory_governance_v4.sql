ALTER TABLE memory_record
    ADD COLUMN IF NOT EXISTS category VARCHAR(64) NULL,
    ADD COLUMN IF NOT EXISTS sensitivity_level VARCHAR(32) NOT NULL DEFAULT 'normal',
    ADD COLUMN IF NOT EXISTS disclosure_policy VARCHAR(32) NOT NULL DEFAULT 'normal',
    ADD COLUMN IF NOT EXISTS lifecycle_state VARCHAR(32) NOT NULL DEFAULT 'fresh',
    ADD COLUMN IF NOT EXISTS stability_score NUMERIC(4, 3) NOT NULL DEFAULT 0.500,
    ADD COLUMN IF NOT EXISTS recall_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_recalled_at TIMESTAMPTZ NULL;

ALTER TABLE memory_inference
    ADD COLUMN IF NOT EXISTS sensitivity_level VARCHAR(32) NOT NULL DEFAULT 'normal',
    ADD COLUMN IF NOT EXISTS disclosure_policy VARCHAR(32) NOT NULL DEFAULT 'normal';

INSERT INTO domain_registry (domain_name, domain_kind, governance_mode, default_value_key, description, is_system)
VALUES
    ('category', 'taxonomy', 'manual_review', 'context', 'Governed analyzer category taxonomy', TRUE),
    ('attribute_key', 'taxonomy', 'manual_review', 'memory', 'Governed slot attribute taxonomy', TRUE)
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
    ('category', 'context', 'context', 'Context-derived durable memory', 'active', TRUE, 'system'),
    ('category', 'preference', 'preference', 'Preference-oriented memory', 'active', TRUE, 'system'),
    ('category', 'current_goal', 'current_goal', 'Current goal or focus', 'active', TRUE, 'system'),
    ('category', 'relationship', 'relationship', 'Relationship-related memory', 'active', TRUE, 'system'),
    ('category', 'sensitive_state', 'sensitive_state', 'Sensitive state memory', 'active', TRUE, 'system'),
    ('category', 'generic_memory', 'generic_memory', 'Generic analyzed memory', 'active', TRUE, 'system'),
    ('category', 'ephemeral', 'ephemeral', 'Transient non-durable signal', 'active', TRUE, 'system'),
    ('attribute_key', 'memory', 'memory', 'Generic memory attribute', 'active', TRUE, 'system'),
    ('attribute_key', 'favorite_drink', 'favorite_drink', 'Favorite drink slot', 'active', TRUE, 'system'),
    ('attribute_key', 'favorite_food', 'favorite_food', 'Favorite food slot', 'active', TRUE, 'system'),
    ('attribute_key', 'personality_trait', 'personality_trait', 'Personality trait slot', 'active', TRUE, 'system'),
    ('attribute_key', 'possible_role', 'possible_role', 'Possible role slot', 'active', TRUE, 'system'),
    ('attribute_key', 'domain_interest', 'domain_interest', 'Domain interest slot', 'active', TRUE, 'system'),
    ('attribute_key', 'current_focus', 'current_focus', 'Current focus slot', 'active', TRUE, 'system'),
    ('attribute_key', 'current_goal', 'current_goal', 'Current goal slot', 'active', TRUE, 'system'),
    ('attribute_key', 'collaboration_rule', 'collaboration_rule', 'Collaboration rule slot', 'active', TRUE, 'system'),
    ('attribute_key', 'life_status', 'life_status', 'Life status slot', 'active', TRUE, 'system'),
    ('attribute_key', 'relationship_fact', 'relationship_fact', 'Relationship fact slot', 'active', TRUE, 'system'),
    ('attribute_key', 'state', 'state', 'State slot', 'active', TRUE, 'system'),
    ('attribute_key', 'ephemeral', 'ephemeral', 'Ephemeral slot', 'active', TRUE, 'system')
ON CONFLICT (domain_name, value_key) DO UPDATE
SET display_name = EXCLUDED.display_name,
    description = EXCLUDED.description,
    status = EXCLUDED.status,
    updated_at = now();

INSERT INTO domain_value_alias (domain_name, alias_key, canonical_value_key)
VALUES
    ('attribute_key', 'self_description', 'personality_trait'),
    ('attribute_key', 'personality', 'personality_trait'),
    ('attribute_key', 'trait', 'personality_trait'),
    ('attribute_key', 'possible_job', 'possible_role'),
    ('attribute_key', 'likely_role', 'possible_role'),
    ('attribute_key', 'topic_interest', 'domain_interest')
ON CONFLICT (domain_name, alias_key) DO UPDATE
SET canonical_value_key = EXCLUDED.canonical_value_key;

ALTER TABLE memory_record
    DROP CONSTRAINT IF EXISTS chk_memory_record_sensitivity_level,
    DROP CONSTRAINT IF EXISTS chk_memory_record_disclosure_policy,
    DROP CONSTRAINT IF EXISTS chk_memory_record_lifecycle_state,
    ADD CONSTRAINT chk_memory_record_sensitivity_level
        CHECK (sensitivity_level IN ('public', 'normal', 'sensitive', 'restricted')) NOT VALID,
    ADD CONSTRAINT chk_memory_record_disclosure_policy
        CHECK (disclosure_policy IN ('normal', 'gentle', 'user_confirm', 'internal_only')) NOT VALID,
    ADD CONSTRAINT chk_memory_record_lifecycle_state
        CHECK (lifecycle_state IN ('fresh', 'stable', 'cold', 'stale', 'conflicted')) NOT VALID;

ALTER TABLE memory_inference
    DROP CONSTRAINT IF EXISTS chk_memory_inference_sensitivity_level,
    DROP CONSTRAINT IF EXISTS chk_memory_inference_disclosure_policy,
    ADD CONSTRAINT chk_memory_inference_sensitivity_level
        CHECK (sensitivity_level IN ('public', 'normal', 'sensitive', 'restricted')) NOT VALID,
    ADD CONSTRAINT chk_memory_inference_disclosure_policy
        CHECK (disclosure_policy IN ('normal', 'gentle', 'user_confirm', 'internal_only')) NOT VALID;

CREATE INDEX IF NOT EXISTS idx_memory_record_lifecycle_updated
    ON memory_record (status, lifecycle_state, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_record_disclosure_recall
    ON memory_record (status, disclosure_policy, sensitivity_level, updated_at DESC);
