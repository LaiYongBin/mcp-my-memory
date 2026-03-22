"""Canonical domain constants for memory service values."""

from __future__ import annotations

from typing import Literal, TypeAlias


DEFAULT_SESSION_KEY = "default"

STATUS_ACTIVE = "active"
STATUS_ARCHIVED = "archived"
STATUS_DELETED = "deleted"
STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"

SOURCE_MANUAL = "manual"
SOURCE_CONVERSATION = "conversation"
SOURCE_REVIEW_APPROVED = "review-approved"
SOURCE_CONSOLIDATION = "consolidation"
SOURCE_ANALYSIS = "analysis"

ACTION_LONG_TERM = "long_term"
ACTION_WORKING_MEMORY = "working_memory"
ACTION_REVIEW = "review"
ACTION_IGNORE = "ignore"

SNAPSHOT_SEGMENT = "segment"
SNAPSHOT_TOPIC = "topic"
SNAPSHOT_GLOBAL_TOPIC = "global_topic"

EVENT_TURN = "turn"
EVENT_SESSION_SYNC = "session_sync"

ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"

EVIDENCE_EXPLICIT = "explicit"
EVIDENCE_OBSERVED = "observed"
EVIDENCE_INFERRED = "inferred"

TIME_LONG_TERM = "long_term"
TIME_MID_TERM = "mid_term"
TIME_SHORT_TERM = "short_term"
TIME_EPHEMERAL = "ephemeral"

CONFLICT_COEXIST = "coexist"
CONFLICT_REPLACE = "replace"
CONFLICT_MERGE = "merge"
CONFLICT_REVIEW = "review"

LIFECYCLE_FRESH = "fresh"
LIFECYCLE_STABLE = "stable"
LIFECYCLE_COLD = "cold"
LIFECYCLE_STALE = "stale"
LIFECYCLE_CONFLICTED = "conflicted"

SENSITIVITY_PUBLIC = "public"
SENSITIVITY_NORMAL = "normal"
SENSITIVITY_SENSITIVE = "sensitive"
SENSITIVITY_RESTRICTED = "restricted"

DISCLOSURE_NORMAL = "normal"
DISCLOSURE_GENTLE = "gentle"
DISCLOSURE_USER_CONFIRM = "user_confirm"
DISCLOSURE_INTERNAL_ONLY = "internal_only"

MEMORY_STATUSES = (STATUS_ACTIVE, STATUS_ARCHIVED, STATUS_DELETED)
CANDIDATE_STATUSES = (STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED)
SESSION_STATUSES = (STATUS_ACTIVE, STATUS_ARCHIVED)
INFERENCE_ACTIONS = (ACTION_LONG_TERM, ACTION_WORKING_MEMORY, ACTION_REVIEW, ACTION_IGNORE)
SNAPSHOT_LEVELS = (SNAPSHOT_SEGMENT, SNAPSHOT_TOPIC, SNAPSHOT_GLOBAL_TOPIC)
EVENT_TYPES = (EVENT_TURN, EVENT_SESSION_SYNC)
CONVERSATION_ROLES = (ROLE_USER, ROLE_ASSISTANT)
SOURCE_TYPES = (
    SOURCE_MANUAL,
    SOURCE_CONVERSATION,
    SOURCE_REVIEW_APPROVED,
    SOURCE_CONSOLIDATION,
    SOURCE_ANALYSIS,
)
EVIDENCE_TYPES = (EVIDENCE_EXPLICIT, EVIDENCE_OBSERVED, EVIDENCE_INFERRED)
TIME_SCOPES = (TIME_LONG_TERM, TIME_MID_TERM, TIME_SHORT_TERM, TIME_EPHEMERAL)
CONFLICT_MODES = (CONFLICT_COEXIST, CONFLICT_REPLACE, CONFLICT_MERGE, CONFLICT_REVIEW)
LIFECYCLE_STATES = (
    LIFECYCLE_FRESH,
    LIFECYCLE_STABLE,
    LIFECYCLE_COLD,
    LIFECYCLE_STALE,
    LIFECYCLE_CONFLICTED,
)
SENSITIVITY_LEVELS = (
    SENSITIVITY_PUBLIC,
    SENSITIVITY_NORMAL,
    SENSITIVITY_SENSITIVE,
    SENSITIVITY_RESTRICTED,
)
DISCLOSURE_POLICIES = (
    DISCLOSURE_NORMAL,
    DISCLOSURE_GENTLE,
    DISCLOSURE_USER_CONFIRM,
    DISCLOSURE_INTERNAL_ONLY,
)

MemoryStatus: TypeAlias = Literal["active", "archived", "deleted"]
CandidateStatus: TypeAlias = Literal["pending", "approved", "rejected"]
SessionStatus: TypeAlias = Literal["active", "archived"]
SourceType: TypeAlias = Literal["manual", "conversation", "review-approved", "consolidation", "analysis"]
InferenceAction: TypeAlias = Literal["long_term", "working_memory", "review", "ignore"]
SnapshotLevel: TypeAlias = Literal["segment", "topic", "global_topic"]
ConversationRole: TypeAlias = Literal["user", "assistant"]
EventType: TypeAlias = Literal["turn", "session_sync"]
EvidenceType: TypeAlias = Literal["explicit", "observed", "inferred"]
TimeScope: TypeAlias = Literal["long_term", "mid_term", "short_term", "ephemeral"]
ConflictMode: TypeAlias = Literal["coexist", "replace", "merge", "review"]
LifecycleState: TypeAlias = Literal["fresh", "stable", "cold", "stale", "conflicted"]
SensitivityLevel: TypeAlias = Literal["public", "normal", "sensitive", "restricted"]
DisclosurePolicy: TypeAlias = Literal["normal", "gentle", "user_confirm", "internal_only"]
