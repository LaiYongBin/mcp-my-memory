ALTER TABLE memory_record
    DROP CONSTRAINT IF EXISTS chk_memory_record_status,
    DROP CONSTRAINT IF EXISTS chk_memory_record_source_type,
    DROP CONSTRAINT IF EXISTS chk_memory_record_confidence,
    DROP CONSTRAINT IF EXISTS chk_memory_record_importance,
    ADD CONSTRAINT chk_memory_record_status
        CHECK (status IN ('active', 'archived', 'deleted')) NOT VALID,
    ADD CONSTRAINT chk_memory_record_source_type
        CHECK (source_type IN ('manual', 'conversation', 'review-approved', 'consolidation', 'analysis')) NOT VALID,
    ADD CONSTRAINT chk_memory_record_confidence
        CHECK (confidence >= 0 AND confidence <= 1) NOT VALID,
    ADD CONSTRAINT chk_memory_record_importance
        CHECK (importance >= 1 AND importance <= 10) NOT VALID;

ALTER TABLE session_state
    DROP CONSTRAINT IF EXISTS chk_session_state_status,
    DROP CONSTRAINT IF EXISTS chk_session_state_importance,
    ADD CONSTRAINT chk_session_state_status
        CHECK (status IN ('active', 'archived')) NOT VALID,
    ADD CONSTRAINT chk_session_state_importance
        CHECK (importance >= 1 AND importance <= 10) NOT VALID;

ALTER TABLE memory_candidate
    DROP CONSTRAINT IF EXISTS chk_memory_candidate_status,
    DROP CONSTRAINT IF EXISTS chk_memory_candidate_confidence,
    ADD CONSTRAINT chk_memory_candidate_status
        CHECK (status IN ('pending', 'approved', 'rejected')) NOT VALID,
    ADD CONSTRAINT chk_memory_candidate_confidence
        CHECK (confidence >= 0 AND confidence <= 1) NOT VALID;

ALTER TABLE conversation_turn
    DROP CONSTRAINT IF EXISTS chk_conversation_turn_event_type,
    DROP CONSTRAINT IF EXISTS chk_conversation_turn_role,
    DROP CONSTRAINT IF EXISTS chk_conversation_turn_analyzed_status,
    ADD CONSTRAINT chk_conversation_turn_event_type
        CHECK (event_type IN ('turn', 'session_sync')) NOT VALID,
    ADD CONSTRAINT chk_conversation_turn_role
        CHECK (role IN ('user', 'assistant')) NOT VALID,
    ADD CONSTRAINT chk_conversation_turn_analyzed_status
        CHECK (analyzed_status IN ('pending', 'done')) NOT VALID;

ALTER TABLE memory_inference
    DROP CONSTRAINT IF EXISTS chk_memory_inference_evidence_type,
    DROP CONSTRAINT IF EXISTS chk_memory_inference_time_scope,
    DROP CONSTRAINT IF EXISTS chk_memory_inference_action,
    DROP CONSTRAINT IF EXISTS chk_memory_inference_status,
    DROP CONSTRAINT IF EXISTS chk_memory_inference_confidence,
    DROP CONSTRAINT IF EXISTS chk_memory_inference_conflict_mode,
    ADD CONSTRAINT chk_memory_inference_evidence_type
        CHECK (evidence_type IN ('explicit', 'observed', 'inferred')) NOT VALID,
    ADD CONSTRAINT chk_memory_inference_time_scope
        CHECK (time_scope IN ('long_term', 'mid_term', 'short_term', 'ephemeral')) NOT VALID,
    ADD CONSTRAINT chk_memory_inference_action
        CHECK (action IN ('long_term', 'working_memory', 'review', 'ignore')) NOT VALID,
    ADD CONSTRAINT chk_memory_inference_status
        CHECK (status IN ('active', 'archived')) NOT VALID,
    ADD CONSTRAINT chk_memory_inference_confidence
        CHECK (confidence >= 0 AND confidence <= 1) NOT VALID,
    ADD CONSTRAINT chk_memory_inference_conflict_mode
        CHECK (conflict_mode IN ('coexist', 'replace', 'merge', 'review')) NOT VALID;

ALTER TABLE memory_signal
    DROP CONSTRAINT IF EXISTS chk_memory_signal_evidence_type,
    DROP CONSTRAINT IF EXISTS chk_memory_signal_time_scope,
    DROP CONSTRAINT IF EXISTS chk_memory_signal_status,
    DROP CONSTRAINT IF EXISTS chk_memory_signal_occurrence_count,
    ADD CONSTRAINT chk_memory_signal_evidence_type
        CHECK (evidence_type IN ('explicit', 'observed', 'inferred')) NOT VALID,
    ADD CONSTRAINT chk_memory_signal_time_scope
        CHECK (time_scope IN ('long_term', 'mid_term', 'short_term', 'ephemeral')) NOT VALID,
    ADD CONSTRAINT chk_memory_signal_status
        CHECK (status IN ('active', 'archived')) NOT VALID,
    ADD CONSTRAINT chk_memory_signal_occurrence_count
        CHECK (occurrence_count >= 0) NOT VALID;

ALTER TABLE conversation_summary
    DROP CONSTRAINT IF EXISTS chk_conversation_summary_snapshot_level,
    DROP CONSTRAINT IF EXISTS chk_conversation_summary_status,
    DROP CONSTRAINT IF EXISTS chk_conversation_summary_turn_count,
    ADD CONSTRAINT chk_conversation_summary_snapshot_level
        CHECK (snapshot_level IN ('segment', 'topic', 'global_topic')) NOT VALID,
    ADD CONSTRAINT chk_conversation_summary_status
        CHECK (status IN ('active', 'archived')) NOT VALID,
    ADD CONSTRAINT chk_conversation_summary_turn_count
        CHECK (turn_count >= 0) NOT VALID;
