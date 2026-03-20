CREATE INDEX IF NOT EXISTS idx_memory_item_user_status
    ON memory_item (user_code, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_item_user_type
    ON memory_item (user_code, memory_type, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_item_tags_gin
    ON memory_item USING GIN (tags);

CREATE INDEX IF NOT EXISTS idx_memory_item_search_vector
    ON memory_item USING GIN (search_vector);

CREATE INDEX IF NOT EXISTS idx_working_memory_user_session
    ON working_memory (user_code, session_key, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_embedding_user_memory
    ON memory_embedding (user_code, memory_id, chunk_index);
