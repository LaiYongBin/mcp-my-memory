CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE memory_embedding
    ADD COLUMN IF NOT EXISTS embedding vector(1536);

CREATE INDEX IF NOT EXISTS idx_memory_embedding_vector_cosine
    ON memory_embedding
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
