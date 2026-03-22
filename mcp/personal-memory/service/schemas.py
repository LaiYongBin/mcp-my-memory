"""Shared request/response models."""

from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

from service.constants import (
    DEFAULT_SESSION_KEY,
    SOURCE_CONVERSATION,
    SOURCE_MANUAL,
    STATUS_ACTIVE,
    ConversationRole,
    MemoryStatus,
    SnapshotLevel,
)


class SearchRequest(BaseModel):
    query: str = Field(default="")
    user_code: Optional[str] = None
    memory_type: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    include_archived: bool = False
    limit: int = Field(default=10, ge=1, le=100)


class UpsertRequest(BaseModel):
    id: Optional[int] = None
    user_code: Optional[str] = None
    memory_type: str = "fact"
    title: str
    content: str
    summary: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    source_type: str = SOURCE_MANUAL
    source_ref: Optional[str] = None
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    importance: int = Field(default=5, ge=1, le=10)
    status: MemoryStatus = STATUS_ACTIVE
    is_explicit: bool = False
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None


class DeleteRequest(BaseModel):
    id: int
    user_code: Optional[str] = None


class ArchiveRequest(BaseModel):
    id: int
    user_code: Optional[str] = None


class PromoteRequest(BaseModel):
    text: str
    title: Optional[str] = None
    user_code: Optional[str] = None
    memory_type: str = "fact"
    tags: List[str] = Field(default_factory=list)
    source_type: str = SOURCE_CONVERSATION
    source_ref: Optional[str] = None
    explicit: bool = False


class CaptureRequest(BaseModel):
    text: str
    user_code: Optional[str] = None
    auto_persist: bool = False


class CaptureCycleRequest(BaseModel):
    user_text: str
    assistant_text: str = ""
    session_key: str = "default"
    source_ref: Optional[str] = None
    user_code: Optional[str] = None
    consolidate: bool = True


class ConsolidateRequest(BaseModel):
    user_code: Optional[str] = None
    session_key: Optional[str] = None


class AnalysisListRequest(BaseModel):
    user_code: Optional[str] = None
    session_key: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=100)


class TurnInput(BaseModel):
    role: ConversationRole
    content: str


class ContextSyncRequest(BaseModel):
    session_key: str = DEFAULT_SESSION_KEY
    turns: List[TurnInput] = Field(default_factory=list)
    user_code: Optional[str] = None
    topic_hint: Optional[str] = None
    source_ref: Optional[str] = None
    extract_memory: bool = False


class ContextSearchRequest(BaseModel):
    query: str = Field(default="")
    user_code: Optional[str] = None
    session_key: Optional[str] = None
    snapshot_level: Optional[SnapshotLevel] = None
    limit: int = Field(default=10, ge=1, le=100)


class ReviewListRequest(BaseModel):
    user_code: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=100)


class ReviewActionRequest(BaseModel):
    id: int
    user_code: Optional[str] = None
    action: str


class ApiResponse(BaseModel):
    ok: bool
    data: Optional[Any] = None
    message: str = ""


MemoryWindowField = Literal["created_at", "updated_at", "valid_from", "valid_to"]


class MCPResultBase(BaseModel):
    ok: bool = True
    message: str = ""


class ItemListResult(MCPResultBase):
    items: List[Dict[str, Any]] = Field(default_factory=list)
    count: int = 0


class MemoryMutationResult(MCPResultBase):
    memory: Dict[str, Any]


class ContextMutationResult(MCPResultBase):
    context: Dict[str, Any]


class CaptureTurnResult(MCPResultBase):
    capture: Dict[str, Any]
    context: Optional[Dict[str, Any]] = None


class DomainMutationResult(MCPResultBase):
    candidate: Dict[str, Any]
    value: Optional[Dict[str, Any]] = None


class AliasMutationResult(MCPResultBase):
    alias: Dict[str, Any]
    candidate: Optional[Dict[str, Any]] = None
    value: Optional[Dict[str, Any]] = None


class MaintenanceResult(MCPResultBase):
    scanned_count: int = 0
    updated_count: int = 0
    dry_run: bool = False
    changed_ids: List[int] = Field(default_factory=list)
    lifecycle_counts: Dict[str, int] = Field(default_factory=dict)
    updated_memories: List[Dict[str, Any]] = Field(default_factory=list)


class TurnOrchestrationResult(MCPResultBase):
    recall: Dict[str, Any] = Field(default_factory=dict)
    should_capture: bool = False
    capture_plan: Dict[str, Any] = Field(default_factory=dict)
    executed_capture: Optional[Dict[str, Any]] = None
    recommended_sequence: List[str] = Field(default_factory=list)


HookKind = Literal["recent_topic", "entity_relation", "preference_hint", "fact_hint"]
HookVisibility = Literal["safe", "internal_only"]
HintConfidenceBand = Literal["low", "medium", "high"]


class HookEntryBase(BaseModel):
    visibility: HookVisibility
    text: str


class RecentTopicHookEntry(HookEntryBase):
    kind: Literal["recent_topic"]
    topic: Optional[str] = None
    summary: Optional[str] = None
    use_priority: Optional[int] = None
    confidence_band: Optional[HintConfidenceBand] = None


class EntityRelationHookEntry(HookEntryBase):
    kind: Literal["entity_relation"]
    subject_key: Optional[str] = None
    display_name: Optional[str] = None
    reasons: List[str] = Field(default_factory=list)
    integration_hint: Optional[str] = None
    use_priority: Optional[int] = None
    confidence_band: Optional[HintConfidenceBand] = None


class PreferenceHintHookEntry(HookEntryBase):
    kind: Literal["preference_hint"]
    memory_id: Optional[int] = None
    memory_title: Optional[str] = None
    attribute_key: Optional[str] = None
    integration_hint: Optional[str] = None
    use_priority: Optional[int] = None
    confidence_band: Optional[HintConfidenceBand] = None


class FactHintHookEntry(HookEntryBase):
    kind: Literal["fact_hint"]
    memory_id: Optional[int] = None
    memory_title: Optional[str] = None
    attribute_key: Optional[str] = None
    integration_hint: Optional[str] = None
    use_priority: Optional[int] = None
    confidence_band: Optional[HintConfidenceBand] = None


HookEntry = Annotated[
    Union[RecentTopicHookEntry, EntityRelationHookEntry, PreferenceHintHookEntry, FactHintHookEntry],
    Field(discriminator="kind"),
]


class RecommendedResponsePlan(BaseModel):
    """调用方可以直接消费的回答规划，无需解读 internal_strategy。"""

    primary_answer_style: str = "answer_normally"
    main_sentence_hint: str = ""
    inline_memories: List[str] = Field(
        default_factory=list,
        description="可直接写进回答的记忆摘要（来自 direct 层）",
    )
    soft_mentions: List[str] = Field(
        default_factory=list,
        description="轻量提及，不喧宾夺主（来自 contextual 层）",
    )
    internal_only: List[str] = Field(
        default_factory=list,
        description="仅供内部参考，不对用户说（来自 suppressed 层 + internal_only hooks）",
    )
    followup_hooks: List[str] = Field(
        default_factory=list,
        description="回答后可轻量延展的话题",
    )


class InternalStrategy(BaseModel):
    # --- 以下字段在 RecallResult 顶层已有同名/同义字段，仅为向后兼容保留 ---
    # style 同 RecallResult.suggested_integration_style
    style: str = "answer_normally"
    # should_recall 同 RecallResult.should_recall
    should_recall: bool = False
    # reasons 同 RecallResult.decision_reasons
    reasons: List[str] = Field(default_factory=list)
    # followup_hooks 同 RecallResult.suggested_followup_hooks
    followup_hooks: List[str] = Field(default_factory=list)
    # --- 以下是 InternalStrategy 独有的细节字段（调用方按需使用）---
    hook_entries: List[HookEntry] = Field(default_factory=list)
    recommended_primary_hook: Optional[HookEntry] = None
    recommended_secondary_hooks: List[HookEntry] = Field(default_factory=list)
    safe_hooks: List[str] = Field(default_factory=list)
    internal_only_hooks: List[str] = Field(default_factory=list)
    disclosure_warnings: List[str] = Field(default_factory=list)


class RecallResult(MCPResultBase):
    query_text: str
    memories: List[Dict[str, Any]] = Field(default_factory=list)
    contexts: List[Dict[str, Any]] = Field(default_factory=list)
    recent_contexts: List[Dict[str, Any]] = Field(default_factory=list)
    related_entities: List[Dict[str, Any]] = Field(default_factory=list)
    direct_memories: List[Dict[str, Any]] = Field(default_factory=list)
    contextual_memories: List[Dict[str, Any]] = Field(default_factory=list)
    expansive_memories: List[Dict[str, Any]] = Field(default_factory=list)
    suppressed_memories: List[Dict[str, Any]] = Field(default_factory=list)
    memory_titles: List[str] = Field(default_factory=list)
    context_topics: List[str] = Field(default_factory=list)
    recent_context_topics: List[str] = Field(default_factory=list)
    memory_count: int = 0
    context_count: int = 0
    recent_context_count: int = 0
    related_entity_count: int = 0
    direct_memory_count: int = 0
    contextual_memory_count: int = 0
    expansive_memory_count: int = 0
    suppressed_memory_count: int = 0
    should_recall: bool = False
    decision_score: float = 0.0
    decision_reasons: List[str] = Field(default_factory=list)
    suggested_integration_style: str = "answer_normally"
    suggested_followup_hooks: List[str] = Field(default_factory=list)
    internal_strategy: InternalStrategy = Field(default_factory=InternalStrategy)
    internal_strategy_summary: str = ""
    disclosure_warnings: List[str] = Field(default_factory=list)
    recommended_response_plan: RecommendedResponsePlan = Field(
        default_factory=RecommendedResponsePlan
    )
