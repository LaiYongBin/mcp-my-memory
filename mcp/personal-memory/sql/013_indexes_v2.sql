CREATE INDEX IF NOT EXISTS idx_memory_record_active_updated_recall
    ON memory_record (user_code, updated_at DESC, importance DESC, confidence DESC)
    WHERE deleted_at IS NULL AND status = 'active';

CREATE INDEX IF NOT EXISTS idx_memory_record_active_created_window
    ON memory_record (user_code, created_at DESC)
    WHERE deleted_at IS NULL AND status = 'active';

CREATE INDEX IF NOT EXISTS idx_memory_record_active_valid_window
    ON memory_record (user_code, valid_from DESC, valid_to DESC)
    WHERE deleted_at IS NULL AND status = 'active';

CREATE INDEX IF NOT EXISTS idx_memory_record_active_type_updated
    ON memory_record (user_code, memory_type, updated_at DESC)
    WHERE deleted_at IS NULL AND status = 'active';

CREATE INDEX IF NOT EXISTS idx_conversation_summary_recent_lookup
    ON conversation_summary (
        user_code,
        session_key,
        snapshot_level,
        (coalesce(ended_at, updated_at, created_at)) DESC
    )
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_conversation_summary_recent_global
    ON conversation_summary (
        user_code,
        snapshot_level,
        (coalesce(ended_at, updated_at, created_at)) DESC
    )
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_conversation_summary_topic_recent
    ON conversation_summary (user_code, topic_key, updated_at DESC)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_session_state_active_recent
    ON session_state (user_code, session_key, updated_at DESC)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_session_state_active_expiry
    ON session_state (user_code, expires_at ASC, updated_at DESC)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_memory_signal_active_recent
    ON memory_signal (user_code, conflict_scope, last_seen_at DESC, support_score DESC)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_memory_signal_active_subject
    ON memory_signal (user_code, subject_key, attribute_key, last_seen_at DESC)
    WHERE status = 'active';
