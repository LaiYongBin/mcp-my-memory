-- 020_indexes_v4.sql
-- 补充 related_subject_key 过滤索引

-- memory_record.related_subject_key 部分索引
-- 解决 _load_related_reference_memories 的全表扫描
CREATE INDEX IF NOT EXISTS idx_memory_record_user_related_subject
    ON memory_record (user_code, related_subject_key, updated_at DESC)
    WHERE deleted_at IS NULL AND status = 'active' AND related_subject_key IS NOT NULL;
