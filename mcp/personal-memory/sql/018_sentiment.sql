-- 018: add sentiment dimension to memory_record and memory_inference

ALTER TABLE memory_record
    ADD COLUMN IF NOT EXISTS sentiment VARCHAR(16) DEFAULT 'neutral'
        CHECK (sentiment IN ('neutral', 'positive', 'negative', 'mixed'));

ALTER TABLE memory_inference
    ADD COLUMN IF NOT EXISTS sentiment VARCHAR(16) DEFAULT 'neutral'
        CHECK (sentiment IN ('neutral', 'positive', 'negative', 'mixed'));
