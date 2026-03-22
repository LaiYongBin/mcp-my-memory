CREATE TABLE IF NOT EXISTS entity_profile (
    id BIGSERIAL PRIMARY KEY,
    user_code VARCHAR(64) NOT NULL,
    subject_key VARCHAR(128) NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    relation_type VARCHAR(64) NOT NULL DEFAULT 'entity',
    memory_count INTEGER NOT NULL DEFAULT 0,
    category_keys JSONB NOT NULL DEFAULT '[]'::jsonb,
    attribute_keys JSONB NOT NULL DEFAULT '[]'::jsonb,
    sensitivity_level VARCHAR(32) NOT NULL DEFAULT 'normal',
    disclosure_policy VARCHAR(32) NOT NULL DEFAULT 'normal',
    latest_memory_id BIGINT NULL REFERENCES memory_record(id) ON DELETE SET NULL,
    first_seen_at TIMESTAMPTZ NULL,
    last_seen_at TIMESTAMPTZ NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_code, subject_key)
);

CREATE TABLE IF NOT EXISTS entity_edge (
    id BIGSERIAL PRIMARY KEY,
    user_code VARCHAR(64) NOT NULL,
    source_subject_key VARCHAR(128) NOT NULL,
    target_subject_key VARCHAR(128) NOT NULL,
    relation_type VARCHAR(64) NOT NULL DEFAULT 'entity',
    evidence_count INTEGER NOT NULL DEFAULT 0,
    sensitivity_level VARCHAR(32) NOT NULL DEFAULT 'normal',
    disclosure_policy VARCHAR(32) NOT NULL DEFAULT 'normal',
    latest_memory_id BIGINT NULL REFERENCES memory_record(id) ON DELETE SET NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_code, source_subject_key, target_subject_key, relation_type, status)
);

WITH subject_rollup AS (
    SELECT
        user_code,
        subject_key,
        CASE
            WHEN subject_key LIKE 'friend_%' THEN 'friend'
            WHEN subject_key LIKE 'partner_%' THEN 'partner'
            WHEN subject_key LIKE 'family_%' THEN 'family'
            WHEN subject_key LIKE 'project_%' THEN 'project'
            WHEN subject_key LIKE 'team_%' THEN 'team'
            WHEN subject_key LIKE 'user_%' OR subject_key = 'user' THEN 'user'
            ELSE 'entity'
        END AS relation_type,
        replace(
            regexp_replace(
                regexp_replace(subject_key, '^(friend|partner|family|project|team|user)_', ''),
                '_+',
                ' ',
                'g'
            ),
            '  ',
            ' '
        ) AS display_name,
        COUNT(*)::int AS memory_count,
        jsonb_agg(DISTINCT category) FILTER (WHERE category IS NOT NULL AND category <> '') AS category_keys,
        jsonb_agg(DISTINCT attribute_key) FILTER (WHERE attribute_key IS NOT NULL AND attribute_key <> '') AS attribute_keys,
        (
            ARRAY_AGG(sensitivity_level ORDER BY
                CASE sensitivity_level
                    WHEN 'restricted' THEN 4
                    WHEN 'sensitive' THEN 3
                    WHEN 'normal' THEN 2
                    WHEN 'public' THEN 1
                    ELSE 0
                END DESC
            )
        )[1] AS sensitivity_level,
        (
            ARRAY_AGG(disclosure_policy ORDER BY
                CASE disclosure_policy
                    WHEN 'internal_only' THEN 4
                    WHEN 'user_confirm' THEN 3
                    WHEN 'gentle' THEN 2
                    WHEN 'normal' THEN 1
                    ELSE 0
                END DESC
            )
        )[1] AS disclosure_policy,
        (ARRAY_AGG(id ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST))[1] AS latest_memory_id,
        MIN(created_at) AS first_seen_at,
        MAX(COALESCE(updated_at, created_at)) AS last_seen_at
    FROM memory_record
    WHERE deleted_at IS NULL
      AND status = 'active'
      AND subject_key IS NOT NULL
      AND subject_key <> ''
    GROUP BY user_code, subject_key
)
INSERT INTO entity_profile (
    user_code, subject_key, display_name, relation_type, memory_count,
    category_keys, attribute_keys, sensitivity_level, disclosure_policy,
    latest_memory_id, first_seen_at, last_seen_at, status
)
SELECT
    user_code,
    subject_key,
    NULLIF(trim(display_name), '')::varchar,
    relation_type,
    memory_count,
    COALESCE(category_keys, '[]'::jsonb),
    COALESCE(attribute_keys, '[]'::jsonb),
    COALESCE(sensitivity_level, 'normal'),
    COALESCE(disclosure_policy, 'normal'),
    latest_memory_id,
    first_seen_at,
    last_seen_at,
    'active'
FROM subject_rollup
ON CONFLICT (user_code, subject_key) DO UPDATE
SET display_name = EXCLUDED.display_name,
    relation_type = EXCLUDED.relation_type,
    memory_count = EXCLUDED.memory_count,
    category_keys = EXCLUDED.category_keys,
    attribute_keys = EXCLUDED.attribute_keys,
    sensitivity_level = EXCLUDED.sensitivity_level,
    disclosure_policy = EXCLUDED.disclosure_policy,
    latest_memory_id = EXCLUDED.latest_memory_id,
    first_seen_at = EXCLUDED.first_seen_at,
    last_seen_at = EXCLUDED.last_seen_at,
    status = EXCLUDED.status,
    updated_at = now();

INSERT INTO entity_edge (
    user_code, source_subject_key, target_subject_key, relation_type, evidence_count,
    sensitivity_level, disclosure_policy, latest_memory_id, status
)
SELECT
    user_code,
    'user',
    subject_key,
    relation_type,
    memory_count,
    sensitivity_level,
    disclosure_policy,
    latest_memory_id,
    'active'
FROM entity_profile
WHERE subject_key <> 'user'
ON CONFLICT (user_code, source_subject_key, target_subject_key, relation_type, status) DO UPDATE
SET evidence_count = EXCLUDED.evidence_count,
    sensitivity_level = EXCLUDED.sensitivity_level,
    disclosure_policy = EXCLUDED.disclosure_policy,
    latest_memory_id = EXCLUDED.latest_memory_id,
    updated_at = now();

CREATE INDEX IF NOT EXISTS idx_entity_profile_user_relation
    ON entity_profile (user_code, relation_type, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_entity_edge_user_source
    ON entity_edge (user_code, source_subject_key, updated_at DESC);
