ALTER TABLE memory_record
    ADD COLUMN IF NOT EXISTS related_subject_key VARCHAR(128) NULL;

ALTER TABLE memory_inference
    ADD COLUMN IF NOT EXISTS related_subject VARCHAR(128) NULL;

CREATE INDEX IF NOT EXISTS idx_memory_record_related_subject
    ON memory_record (user_code, related_subject_key, updated_at DESC)
    WHERE related_subject_key IS NOT NULL;
