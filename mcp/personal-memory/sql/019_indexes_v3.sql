-- 019_indexes_v3.sql
-- 补齐缺失索引

-- 1. entity_edge.target_subject_key 独立索引
--    解决 search_entity_relationships 的 OR 条件右侧无法走索引问题
CREATE INDEX IF NOT EXISTS idx_entity_edge_user_target
    ON entity_edge (user_code, target_subject_key)
    WHERE status = 'active';

-- 2. memory_candidate 表索引（原来完全无索引）
--    解决 list_review_candidates 全表扫描
CREATE INDEX IF NOT EXISTS idx_memory_candidate_user_status
    ON memory_candidate (user_code, status, updated_at DESC);

-- 3. memory_record.sentiment 过滤索引
--    解决 search_memories sentiment 参数过滤的全表扫描
CREATE INDEX IF NOT EXISTS idx_memory_record_sentiment
    ON memory_record (user_code, sentiment)
    WHERE deleted_at IS NULL AND status = 'active';

-- 4. memory_record (user_code, subject_key, updated_at DESC) 部分索引
--    优化 entity_graph._load_subject_memories 的查询路径
CREATE INDEX IF NOT EXISTS idx_memory_record_user_subject_updated
    ON memory_record (user_code, subject_key, updated_at DESC)
    WHERE deleted_at IS NULL AND status = 'active' AND subject_key IS NOT NULL;
