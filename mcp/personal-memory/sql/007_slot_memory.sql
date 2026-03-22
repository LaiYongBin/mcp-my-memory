ALTER TABLE memory_item
    ADD COLUMN IF NOT EXISTS subject_key VARCHAR(128) NULL,
    ADD COLUMN IF NOT EXISTS attribute_key VARCHAR(128) NULL,
    ADD COLUMN IF NOT EXISTS value_text TEXT NULL,
    ADD COLUMN IF NOT EXISTS conflict_scope VARCHAR(255) NULL;

ALTER TABLE memory_analysis_result
    ADD COLUMN IF NOT EXISTS attribute VARCHAR(128) NULL,
    ADD COLUMN IF NOT EXISTS value TEXT NULL,
    ADD COLUMN IF NOT EXISTS conflict_scope VARCHAR(255) NULL,
    ADD COLUMN IF NOT EXISTS conflict_mode VARCHAR(32) NOT NULL DEFAULT 'coexist';

CREATE INDEX IF NOT EXISTS idx_memory_item_user_conflict_scope
    ON memory_item (user_code, conflict_scope, updated_at DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_memory_item_user_subject_attribute
    ON memory_item (user_code, subject_key, attribute_key, updated_at DESC)
    WHERE deleted_at IS NULL;
