"""Local MCP server for personal memory tools."""

from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import logging

# context sync 专用后台线程池（fire-and-forget）
_context_sync_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="ctx-sync")
import os
import time as _time_module
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

from service.constants import (
    DISCLOSURE_INTERNAL_ONLY,
    DEFAULT_SESSION_KEY,
    RECALL_SCORE_WEIGHTS,
    SNAPSHOT_SEGMENT,
    SNAPSHOT_TOPIC,
    SOURCE_MANUAL,
    STATUS_ACTIVE,
)
from service.capture_cycle import list_working_memories, run_capture_cycle, _pair_turns
from service.context_snapshots import (
    search_context_snapshots,
    search_recent_context_summaries,
    sync_session_context,
)
from service.domain_registry import (
    approve_domain_candidate,
    list_domain_candidates,
    list_domain_values,
    merge_domain_alias,
    reject_domain_candidate,
)
from service.entity_graph import (
    find_two_hop_connections,
    infer_edge_relation_type,
    rebuild_entity_graph,
    search_entities,
    search_entity_relationships,
    update_entity_profile,
    delete_entity_profile,
    delete_entity_edge,
)
from service.entity_memory import summarize_entities_from_memories
from service.evidence import list_evidence
from service.memory_ops import (
    approve_review_candidate,
    archive_memory,
    delete_memory as delete_memory_row,
    export_memory_records,
    fetch_source_turns,
    generate_memory_report,
    get_memory,
    get_memory_timeline,
    get_stale_for_challenge,
    list_review_candidates,
    maintain_memory_store,
    mark_memories_recalled,
    merge_duplicate_memories,
    reject_review_candidate,
    search_memories,
    search_memories_by_time_range,
    revert_memory_to_version,
    submit_challenge_answer,
    upsert_memory,
)
from service.memory_governance import apply_memory_governance
from service.schemas import (
    AliasMutationResult,
    CaptureTurnResult,
    ContextMutationResult,
    DomainMutationResult,
    ExportResult,
    IngestResult,
    ItemListResult,
    MaintenanceResult,
    MemoryMutationResult,
    MemoryReport,
    MemoryWindowField,
    MergeResult,
    RecallResult,
    RecommendedResponsePlan,
    ReviewCandidate,
    ReviewCandidateList,
    TurnOrchestrationResult,
    WorkingMemory,
    WorkingMemoryList,
)


# B2: per-session turn counter (process-local, resets on restart)
_session_turn_counts: Dict[str, int] = {}


# Task 5: 两跳推理进程内缓存（TTL=300s）
_two_hop_cache: Dict[tuple, tuple] = {}
_TWO_HOP_TTL = 300


def _cached_two_hop(source_keys: List[str], user_code: Optional[str]) -> List[Dict]:
    """带 TTL 缓存的两跳推理查询。"""
    key = (frozenset(source_keys), user_code or "")
    cached = _two_hop_cache.get(key)
    if cached and _time_module.monotonic() < cached[1]:
        return cached[0]
    result = find_two_hop_connections(
        source_subject_keys=source_keys,
        exclude_subject_keys=source_keys,
        user_code=user_code,
    )
    if len(_two_hop_cache) > 1000:
        now = _time_module.monotonic()
        expired = [k for k, v in _two_hop_cache.items() if v[1] < now]
        for k in expired:
            _two_hop_cache.pop(k, None)
    _two_hop_cache[key] = (result, _time_module.monotonic() + _TWO_HOP_TTL)
    return result


def _increment_turn_count(session_key: str) -> int:
    count = _session_turn_counts.get(session_key, 0) + 1
    _session_turn_counts[session_key] = count
    return count


def _service_host() -> str:
    return os.environ.get("LYB_SKILL_MEMORY_SERVICE_HOST", "127.0.0.1")


def _service_port() -> int:
    return int(os.environ.get("LYB_SKILL_MEMORY_SERVICE_PORT", "8787"))


def _compose_recall_query(
    user_message: str, draft_response: Optional[str] = None, topic_hint: Optional[str] = None
) -> str:
    parts = [user_message.strip()]
    if topic_hint and topic_hint.strip():
        parts.append(topic_hint.strip())
    if draft_response and draft_response.strip():
        parts.append(draft_response.strip())
    return " ".join(part for part in parts if part)


# 触发个性化召回的短语模式——使用短语而非单字，避免高频词误判
PERSONAL_QUERY_PATTERNS = (
    "之前",
    "上次",
    "记得",
    "偏好",
    "喜欢",
    "朋友",
    "对象",
    "家人",
    "项目",
    "我们",
    "适合我",
    "推荐给我",
    "提醒我",
    "你知道我",
    "你记得",
)

PERSONAL_MEMORY_PATTERNS = (
    "朋友",
    "对象",
    "家人",
    "喜欢",
    "偏好",
    "favorite_",
    "兴趣爱好",
    "健康",
    "高血压",
    "项目",
    "规则",
)


_PHRASE_STOPWORDS = frozenset({
    "工作", "我们", "时候", "可以", "一个", "这个", "那个", "什么",
    "如何", "怎么", "为什么", "为什", "因为", "所以", "但是", "然后", "现在",
    "已经", "还是", "还有", "或者", "并且", "这样", "那样", "一些",
    "很多", "非常", "特别", "感觉", "觉得", "认为", "知道", "看到",
    # 注意：停用词集仅覆盖已知高频词，滑窗算法本身可能产生无意义子串匹配
})


def _normalized_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(_normalized_text(item) for item in value)
    return str(value).strip().lower()


def _has_pattern(text: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern.lower() in text for pattern in patterns)


def _has_negated_pattern(text: str, patterns: tuple[str, ...], negation_chars: str = "不没别未无非") -> bool:
    """若匹配位置紧前 2 字含否定词，视为否定命中，跳过；否则等同 _has_pattern。
    注意：否定词集仅覆盖单字否定词，不覆盖「没有」「不是」等二字结构。"""
    for pattern in patterns:
        start = 0
        while True:
            idx = text.find(pattern, start)
            if idx < 0:
                break
            prefix = text[max(0, idx - 2):idx]
            if not any(neg in prefix for neg in negation_chars):
                return True
            start = idx + 1
    return False


def _memory_strength(item: Dict[str, Any]) -> float:
    confidence = float(item.get("confidence", 0.0) or 0.0)
    explicit_bonus = 0.15 if item.get("is_explicit") else 0.0
    hybrid_score = float(item.get("hybrid_score", item.get("rank_score", 0.0)) or 0.0)
    semantic_bonus = min(hybrid_score, 0.4)
    return min(confidence + explicit_bonus + semantic_bonus, 1.0)


def _context_strength(item: Dict[str, Any]) -> float:
    topic = _normalized_text(item.get("topic"))
    summary = _normalized_text(item.get("summary"))
    if not topic and not summary:
        return 0.0
    return 0.45 if topic else 0.3


def _shared_phrase_relevance(left: str, right: str) -> float:
    left = "".join(left.split())
    right = "".join(right.split())
    if not left or not right:
        return 0.0
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    max_window = min(4, len(shorter))
    for window in range(max_window, 1, -1):
        for index in range(0, len(shorter) - window + 1):
            phrase = shorter[index : index + window]
            if phrase and phrase in longer:
                if phrase in _PHRASE_STOPWORDS:
                    continue
                return 0.55 if window >= 3 else 0.45
    return 0.0


def _memory_relevance(item: Dict[str, Any], query_text: str) -> float:
    item_text = _normalized_text(
        [
            item.get("title"),
            item.get("content"),
            item.get("summary"),
            item.get("attribute_key"),
            item.get("value_text"),
        ]
    )
    return max(
        float(item.get("hybrid_score", 0.0) or 0.0),
        float(item.get("vector_score", 0.0) or 0.0),
        float(item.get("rank_score", 0.0) or 0.0),
        _shared_phrase_relevance(item_text, query_text),
    )


def _bucket_recall_memories(
    memories: List[Dict[str, Any]], query_text: str
) -> Dict[str, List[Dict[str, Any]]]:
    direct: List[Dict[str, Any]] = []
    contextual: List[Dict[str, Any]] = []
    expansive: List[Dict[str, Any]] = []
    suppressed: List[Dict[str, Any]] = []
    for raw_item in memories:
        item = apply_memory_governance(raw_item)
        disclosure_policy = str(item.get("disclosure_policy") or "")
        relevance = _memory_relevance(item, query_text)
        if disclosure_policy == DISCLOSURE_INTERNAL_ONLY:
            suppressed.append(item)
            continue
        if relevance >= 0.55:
            direct.append(item)
        elif relevance >= 0.4:
            contextual.append(item)
        else:
            expansive.append(item)
    return {
        "direct": direct,
        "contextual": contextual,
        "expansive": expansive,
        "suppressed": suppressed,
    }


def _build_followup_hook_entries(
    *,
    query_text: str,
    recent_contexts: List[Dict[str, Any]],
    direct_memories: Optional[List[Dict[str, Any]]] = None,
    related_entities: Optional[List[Dict[str, Any]]] = None,
    limit: int = 3,
) -> List[Dict[str, Any]]:
    hooks: List[Dict[str, Any]] = []
    for item in recent_contexts:
        topic = str(item.get("topic") or "").strip()
        summary = str(item.get("summary") or "").strip()
        if not topic or not summary:
            continue
        hook = {
            "kind": "recent_topic",
            "visibility": "safe",
            "text": f"recent topic: {topic} -> {summary[:80]}",
            "topic": topic,
            "summary": summary,
            "use_priority": 40,
            "confidence_band": "medium",
        }
        if hook["text"] not in {item["text"] for item in hooks}:
            hooks.append(hook)
        if len(hooks) >= limit:
            break
    for item in direct_memories or []:
        memory_id = item.get("id")
        title = str(item.get("title") or "").strip()
        attribute_key = str(item.get("attribute_key") or "").strip()
        confidence = float(item.get("confidence", 0.0) or 0.0)
        if not title:
            continue
        is_preference_hint = (
            attribute_key.startswith("favorite_")
            or "喜欢" in title
            or "偏好" in title
            or "最喜欢" in str(item.get("content") or "")
        )
        integration_hint = "gentle_personalization" if is_preference_hint else "answer_normally"
        if confidence >= 0.9:
            confidence_band = "high"
        elif confidence >= 0.7:
            confidence_band = "medium"
        else:
            confidence_band = "low"
        if is_preference_hint:
            use_priority = 90 if confidence_band == "high" else 80 if confidence_band == "medium" else 70
        else:
            use_priority = 60 if confidence_band in {"high", "medium"} else 50
        text = (
            f"记忆提示：{title}；"
            + ("可直接作为轻量个性化信息融合。" if integration_hint == "gentle_personalization" else "仅在确实相关时再自然带出。")
        )
        hook = {
            "kind": "preference_hint" if is_preference_hint else "fact_hint",
            "visibility": "safe",
            "text": text,
            "memory_id": int(memory_id) if memory_id is not None else None,
            "memory_title": title,
            "attribute_key": attribute_key or None,
            "integration_hint": integration_hint,
            "use_priority": use_priority,
            "confidence_band": confidence_band,
        }
        if hook["text"] not in {entry["text"] for entry in hooks}:
            hooks.append(hook)
        if len(hooks) >= limit:
            break
    for entity in related_entities or []:
        subject_key = str(entity.get("subject_key") or "").strip()
        display_name = str(entity.get("display_name") or "").strip()
        reasons = [str(reason).strip() for reason in list(entity.get("relationship_reasons") or []) if str(reason).strip()]
        integration_hint = str(entity.get("suggested_integration_hint") or "").strip()
        if not subject_key or not reasons:
            continue
        label = display_name or subject_key
        visibility = "internal_only" if integration_hint == "internal_reference_only" else "safe"
        confidence_band = "high" if len(reasons) >= 1 else "medium"
        if integration_hint == "internal_reference_only":
            use_priority = 85
        elif integration_hint == "mention_with_reason":
            use_priority = 75
        elif integration_hint == "gentle_reference":
            use_priority = 65
        else:
            use_priority = 55
        disclosure_tail = "仅供内部参考。" if visibility == "internal_only" else "可按语气自然融合。"
        hook = {
            "kind": "entity_relation",
            "visibility": visibility,
            "text": (
                f"内部线索：{label}（{subject_key}）与当前话题相关，"
                f"关系点是 {', '.join(reasons)}；{disclosure_tail}"
            ),
            "subject_key": subject_key,
            "display_name": label,
            "reasons": reasons,
            "integration_hint": integration_hint or "answer_normally",
            "use_priority": use_priority,
            "confidence_band": confidence_band,
        }
        if hook["text"] not in {item["text"] for item in hooks}:
            hooks.append(hook)
        if len(hooks) >= limit:
            break
    return sorted(
        hooks,
        key=lambda item: (
            -int(item.get("use_priority", 0) or 0),
            str(item.get("kind") or ""),
            str(item.get("text") or ""),
        ),
    )


def _build_followup_hooks(
    *,
    query_text: str,
    recent_contexts: List[Dict[str, Any]],
    direct_memories: Optional[List[Dict[str, Any]]] = None,
    related_entities: Optional[List[Dict[str, Any]]] = None,
    limit: int = 3,
) -> List[str]:
    entries = _build_followup_hook_entries(
        query_text=query_text,
        recent_contexts=recent_contexts,
        direct_memories=direct_memories,
        related_entities=related_entities,
        limit=limit,
    )
    return [str(item.get("text") or "") for item in entries if str(item.get("text") or "").strip()]


def _integration_hint_for_entity(
    *, reasons: List[str], disclosure_policy: str
) -> str:
    if disclosure_policy == DISCLOSURE_INTERNAL_ONLY:
        return "internal_reference_only"
    if any(reason in {"responsible_for", "collaborates_with", "participates_in"} for reason in reasons):
        return "mention_with_reason"
    if reasons:
        return "gentle_reference"
    return "answer_normally"


def _enrich_related_entities(
    *,
    entities: List[Dict[str, Any]],
    memories: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not entities:
        return []
    # 预建索引，避免 O(entities × memories) 的嵌套扫描
    mem_by_subject: Dict[str, List[Dict[str, Any]]] = {}
    for m in memories:
        sk = str(m.get("subject_key") or "").strip()
        if sk:
            mem_by_subject.setdefault(sk, []).append(m)
    enriched: List[Dict[str, Any]] = []
    for entity in entities:
        subject_key = str(entity.get("subject_key") or "").strip()
        entity_memories = [
            item
            for item in mem_by_subject.get(subject_key, [])
            if _memory_relevance(item, subject_key) >= 0.40
        ]
        relationship_reasons: List[str] = []
        for item in entity_memories:
            reason = infer_edge_relation_type(item)
            if reason and reason not in relationship_reasons:
                relationship_reasons.append(reason)
        enriched.append(
            {
                **entity,
                "relationship_reasons": relationship_reasons,
                "top_relationship_reason": relationship_reasons[0] if relationship_reasons else None,
                "suggested_integration_hint": _integration_hint_for_entity(
                    reasons=relationship_reasons,
                    disclosure_policy=str(entity.get("disclosure_policy") or "normal"),
                ),
            }
        )
    return enriched


def _build_response_plan(
    *,
    suggested_integration_style: str,
    direct_memories: List[Dict[str, Any]],
    contextual_memories: List[Dict[str, Any]],
    suppressed_memories: List[Dict[str, Any]],
    safe_hooks: List[str],
    internal_only_hooks: List[str],
) -> RecommendedResponsePlan:
    inline_memories = [
        str(item.get("title") or "")
        for item in direct_memories
        if item.get("title")
    ]
    soft_mentions = [
        str(item.get("title") or "")
        for item in contextual_memories
        if item.get("title")
    ]
    internal_only: List[str] = [
        str(item.get("title") or "")
        for item in suppressed_memories
        if item.get("title")
    ] + list(internal_only_hooks)

    main_sentence_hint = ""
    if inline_memories and suggested_integration_style == "direct_personalization":
        main_sentence_hint = f"主句直接融入：{inline_memories[0]}"
    elif inline_memories and suggested_integration_style == "gentle_personalization":
        main_sentence_hint = f"轻量带入：{inline_memories[0]}，保持自然语气"
    elif soft_mentions and suggested_integration_style == "gentle_personalization":
        main_sentence_hint = f"可轻量提及：{soft_mentions[0]}"

    return RecommendedResponsePlan(
        primary_answer_style=suggested_integration_style,
        main_sentence_hint=main_sentence_hint,
        inline_memories=inline_memories,
        soft_mentions=soft_mentions,
        internal_only=internal_only,
        followup_hooks=list(safe_hooks),
    )


def _build_internal_strategy_summary(
    *,
    suggested_integration_style: str,
    decision_reasons: List[str],
    suggested_followup_hooks: List[str],
) -> str:
    parts = [f"style={suggested_integration_style}"]
    if decision_reasons:
        parts.append("reasons=" + ", ".join(decision_reasons[:3]))
    if suggested_followup_hooks:
        summary_hooks = list(suggested_followup_hooks[:1])
        internal_hook = next((hook for hook in suggested_followup_hooks if "仅供内部参考" in str(hook)), None)
        if internal_hook and internal_hook not in summary_hooks:
            summary_hooks.append(str(internal_hook))
        for hook in suggested_followup_hooks[1:]:
            if len(summary_hooks) >= 2:
                break
            if hook not in summary_hooks:
                summary_hooks.append(str(hook))
        parts.append("hooks=" + " | ".join(summary_hooks))
    return "; ".join(parts)


def _partition_followup_hooks(hooks: List[str]) -> tuple[List[str], List[str]]:
    safe_hooks: List[str] = []
    internal_only_hooks: List[str] = []
    for hook in hooks:
        if "仅供内部参考" in str(hook):
            internal_only_hooks.append(hook)
        else:
            safe_hooks.append(hook)
    return safe_hooks, internal_only_hooks


def _select_recommended_primary_hook(hook_entries: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not hook_entries:
        return None
    safe_entries = [entry for entry in hook_entries if str(entry.get("visibility") or "") == "safe"]
    if safe_entries:
        return dict(safe_entries[0])
    return dict(hook_entries[0])


def _select_recommended_secondary_hooks(
    hook_entries: List[Dict[str, Any]],
    primary_hook: Optional[Dict[str, Any]],
    *,
    limit: int = 2,
) -> List[Dict[str, Any]]:
    if not hook_entries or limit <= 0:
        return []
    selected: List[Dict[str, Any]] = []
    primary_text = str((primary_hook or {}).get("text") or "")
    safe_entries = [entry for entry in hook_entries if str(entry.get("visibility") or "") == "safe"]
    internal_entries = [entry for entry in hook_entries if str(entry.get("visibility") or "") == "internal_only"]
    for entry in safe_entries + internal_entries:
        if len(selected) >= limit:
            break
        if primary_text and str(entry.get("text") or "") == primary_text:
            continue
        selected.append(dict(entry))
    return selected


def _decide_recall(
    *,
    user_message: str,
    draft_response: Optional[str],
    topic_hint: Optional[str],
    memories: List[Dict[str, Any]],
    contexts: List[Dict[str, Any]],
) -> Dict[str, Any]:
    query_text = _normalized_text([user_message, draft_response, topic_hint])
    top_memory = memories[0] if memories else None
    top_context = contexts[0] if contexts else None

    top_memory_strength = _memory_strength(top_memory or {})
    top_memory_relevance = _memory_relevance(top_memory or {}, query_text)
    top_context_strength = _context_strength(top_context or {})
    query_has_personal_signal = _has_negated_pattern(query_text, PERSONAL_QUERY_PATTERNS)

    memory_signal_text = _normalized_text(
        [
            (top_memory or {}).get("title"),
            (top_memory or {}).get("content"),
            (top_memory or {}).get("summary"),
            (top_memory or {}).get("subject_key"),
            (top_memory or {}).get("attribute_key"),
            (top_memory or {}).get("value_text"),
            (top_memory or {}).get("tags", []),
        ]
    )
    memory_has_personal_signal = _has_pattern(memory_signal_text, PERSONAL_MEMORY_PATTERNS)

    score = 0.0
    reasons: List[str] = []

    if top_memory_strength >= 0.85:
        score += RECALL_SCORE_WEIGHTS["high_confidence_memory"]
        reasons.append("high-confidence memory")
    elif top_memory_strength >= 0.65:
        score += RECALL_SCORE_WEIGHTS["usable_memory_match"]
        reasons.append("usable memory match")

    if top_memory and top_memory.get("is_explicit"):
        score += RECALL_SCORE_WEIGHTS["explicit_memory"]
        reasons.append("explicit memory")

    if top_memory_relevance >= 0.55:
        score += RECALL_SCORE_WEIGHTS["strong_semantic"]
        reasons.append("strong semantic relevance")
    elif top_memory_relevance >= 0.45:
        score += RECALL_SCORE_WEIGHTS["moderate_semantic"]
        reasons.append("moderate semantic relevance")

    if memory_has_personal_signal:
        score += RECALL_SCORE_WEIGHTS["personal_memory_signal"]
        reasons.append("personal link in retrieved memory")

    if query_has_personal_signal:
        score += RECALL_SCORE_WEIGHTS["personal_query_signal"]
        reasons.append("personalization opportunity in current turn")

    if topic_hint and top_context_strength >= 0.4:
        score += RECALL_SCORE_WEIGHTS["topic_continuity"]
        reasons.append("ongoing topic continuity")

    if not query_has_personal_signal and top_memory_relevance < 0.45:
        score = min(score, 0.3)

    should_recall = score >= 0.45 and bool(memories or contexts)
    if not should_recall:
        reasons = ["no strong personalization signal"]
        style = "answer_normally"
    elif query_has_personal_signal and any(
        token in _normalized_text(user_message) for token in ("之前", "上次", "记得", "最喜欢")
    ):
        style = "direct_personalization"
    else:
        style = "gentle_personalization"

    return {
        "should_recall": should_recall,
        "decision_score": round(min(score, 1.0), 4),
        "decision_reasons": reasons,
        "suggested_integration_style": style,
    }


def _build_recall_result(
    *,
    user_message: str,
    draft_response: Optional[str] = None,
    topic_hint: Optional[str] = None,
    user_code: Optional[str] = None,
    memory_limit: int = 3,
    context_limit: int = 3,
    recent_context_limit: int = 2,
    recent_context_hours: int = 168,
    include_cited_sources: bool = False,
) -> RecallResult:
    query_text = _compose_recall_query(
        user_message=user_message, draft_response=draft_response, topic_hint=topic_hint
    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        f_memories = executor.submit(
            search_memories,
            query=query_text, user_code=user_code, include_archived=False, limit=memory_limit,
        )
        f_contexts = executor.submit(
            search_context_snapshots,
            query=query_text, user_code=user_code, snapshot_level=None, session_key=None, limit=context_limit,
        )
        f_recent = executor.submit(
            search_recent_context_summaries,
            user_code=user_code, session_key=None, query="", snapshot_levels=[SNAPSHOT_SEGMENT, SNAPSHOT_TOPIC],
            recent_hours=recent_context_hours, limit=recent_context_limit,
        )
        try:
            memories = f_memories.result()
        except Exception as e:
            logging.getLogger(__name__).warning("memories fetch failed: %s", e)
            memories = []
        try:
            contexts = f_contexts.result()
        except Exception as e:
            logging.getLogger(__name__).warning("contexts fetch failed: %s", e)
            contexts = []
        try:
            recent_contexts = f_recent.result()
        except Exception as e:
            logging.getLogger(__name__).warning("recent_contexts fetch failed: %s", e)
            recent_contexts = []
    memory_groups = _bucket_recall_memories(memories, query_text)
    visible_memories = memory_groups["direct"] + memory_groups["contextual"]
    related_entities = summarize_entities_from_memories(
        visible_memories + memory_groups["suppressed"] + memory_groups["expansive"],
        limit=5,
    )
    related_entities = _enrich_related_entities(
        entities=related_entities,
        memories=visible_memories + memory_groups["suppressed"] + memory_groups["expansive"],
    )
    # E3: 一阶实体加上 hop=1 标记
    for entity in related_entities:
        entity.setdefault("hop", 1)
        entity.setdefault("via_entity", None)

    # E3: 查找二阶实体
    source_keys = [e["subject_key"] for e in related_entities if e.get("subject_key")]
    if source_keys:
        two_hop_rows = _cached_two_hop(source_keys, user_code)
        for row in two_hop_rows:
            related_entities.append({
                **row,
                "hop": 2,
                "visibility": "internal_only",
            })
    decision = _decide_recall(
        user_message=user_message,
        draft_response=draft_response,
        topic_hint=topic_hint,
        memories=visible_memories,
        contexts=contexts,
    )
    if visible_memories:
        try:
            mark_memories_recalled(
                [int(item["id"]) for item in visible_memories if item.get("id")],
                user_code,
            )
        except Exception:
            pass
    hook_entries = _build_followup_hook_entries(
        query_text=query_text,
        recent_contexts=recent_contexts,
        direct_memories=memory_groups["direct"],
        related_entities=related_entities,
    )
    followup_hooks = [str(item.get("text") or "") for item in hook_entries if str(item.get("text") or "").strip()]
    disclosure_warnings = [
        f"{item.get('title')}: {item.get('disclosure_policy')}"
        for item in memory_groups["suppressed"]
        if item.get("title")
    ]
    safe_hooks, internal_only_hooks = _partition_followup_hooks(list(followup_hooks))
    recommended_primary_hook = _select_recommended_primary_hook(list(hook_entries))
    recommended_secondary_hooks = _select_recommended_secondary_hooks(
        list(hook_entries),
        recommended_primary_hook,
        limit=2,
    )
    cited_sources = []
    if include_cited_sources:
        source_refs = [m.get("source_ref") for m in memories if m.get("source_ref")]
        if source_refs:
            source_map = fetch_source_turns(source_refs)
            cited_sources = list(source_map.values())
    internal_strategy = {
        "style": str(decision["suggested_integration_style"]),
        "should_recall": bool(decision["should_recall"]),
        "reasons": list(decision["decision_reasons"]),
        "followup_hooks": list(followup_hooks),
        "hook_entries": list(hook_entries),
        "recommended_primary_hook": recommended_primary_hook,
        "recommended_secondary_hooks": recommended_secondary_hooks,
        "safe_hooks": safe_hooks,
        "internal_only_hooks": internal_only_hooks,
        "disclosure_warnings": list(disclosure_warnings),
    }
    internal_strategy_summary = _build_internal_strategy_summary(
        suggested_integration_style=str(decision["suggested_integration_style"]),
        decision_reasons=list(decision["decision_reasons"]),
        suggested_followup_hooks=followup_hooks,
    )
    response_plan = _build_response_plan(
        suggested_integration_style=str(decision["suggested_integration_style"]),
        direct_memories=memory_groups["direct"],
        contextual_memories=memory_groups["contextual"],
        suppressed_memories=memory_groups["suppressed"],
        safe_hooks=safe_hooks,
        internal_only_hooks=internal_only_hooks,
    )
    # E4: 计算 dominant_sentiment
    sentiments = [m.get("sentiment", "neutral") for m in memory_groups["direct"]]
    if sentiments:
        from collections import Counter
        dominant_sentiment = Counter(sentiments).most_common(1)[0][0]
    else:
        dominant_sentiment = "neutral"
    tone_hint = {
        "positive": "match_positive",
        "negative": "acknowledge_negative",
    }.get(dominant_sentiment, "neutral")
    response_plan.tone_hint = tone_hint
    return RecallResult(
        query_text=query_text,
        memories=visible_memories,
        contexts=contexts,
        recent_contexts=recent_contexts,
        related_entities=related_entities,
        direct_memories=memory_groups["direct"],
        contextual_memories=memory_groups["contextual"],
        expansive_memories=memory_groups["expansive"],
        suppressed_memories=memory_groups["suppressed"],
        memory_titles=[str(item.get("title") or "") for item in visible_memories if item.get("title")],
        context_topics=[str(item.get("topic") or "") for item in contexts if item.get("topic")],
        recent_context_topics=[str(item.get("topic") or "") for item in recent_contexts if item.get("topic")],
        memory_count=len(visible_memories),
        context_count=len(contexts),
        recent_context_count=len(recent_contexts),
        related_entity_count=len(related_entities),
        direct_memory_count=len(memory_groups["direct"]),
        contextual_memory_count=len(memory_groups["contextual"]),
        expansive_memory_count=len(memory_groups["expansive"]),
        suppressed_memory_count=len(memory_groups["suppressed"]),
        should_recall=bool(decision["should_recall"]),
        decision_score=float(decision["decision_score"]),
        decision_reasons=list(decision["decision_reasons"]),
        suggested_integration_style=str(decision["suggested_integration_style"]),
        suggested_followup_hooks=followup_hooks,
        internal_strategy=internal_strategy,
        internal_strategy_summary=internal_strategy_summary,
        disclosure_warnings=disclosure_warnings,
        cited_sources=cited_sources,
        recommended_response_plan=response_plan,
        dominant_sentiment=dominant_sentiment,
    )


def _execute_capture_turn(
    *,
    user_text: str,
    assistant_text: str = "",
    session_key: str = DEFAULT_SESSION_KEY,
    user_code: Optional[str] = None,
    topic_hint: Optional[str] = None,
    source_ref: Optional[str] = None,
    consolidate: bool = True,
    sync_context: bool = True,
) -> CaptureTurnResult:
    capture = run_capture_cycle(
        user_text=user_text,
        assistant_text=assistant_text,
        user_code=user_code,
        session_key=session_key,
        source_ref=source_ref,
        consolidate=consolidate,
    )
    if sync_context:
        # fire-and-forget：将 LLM 摘要任务提交到后台线程，不等待结果
        _context_sync_executor.submit(
            sync_session_context,
            session_key=session_key,
            turns=None,
            user_code=user_code,
            topic_hint=topic_hint,
            source_ref=source_ref,
            extract_memory=False,
        )
    return CaptureTurnResult(capture=capture, context=None)


def create_server(
    *,
    host: Optional[str] = None,
    port: Optional[int] = None,
    streamable_http_path: Optional[str] = None,
) -> FastMCP:
    server = FastMCP(
        name="personal-memory",
        instructions=(
            "Use these tools to store durable personal memory, sync context, and recall "
            "relevant memories before answering when it improves personalization or continuity."
        ),
        host=host or _service_host(),
        port=port or _service_port(),
        streamable_http_path=streamable_http_path or "/mcp",
    )

    @server.tool(name="get_memory", structured_output=True)
    def get_memory_tool(
        id: int,
        user_code: Optional[str] = None,
    ) -> MemoryMutationResult:
        memory = get_memory(id, user_code)
        if not memory:
            raise ValueError(f"memory {id} not found")
        return MemoryMutationResult(memory=memory)

    @server.tool(name="search_memories", structured_output=True)
    def search_memories_tool(
        query: str = "",
        user_code: Optional[str] = None,
        memory_type: Optional[str] = None,
        tags: Optional[list[str]] = None,
        include_archived: bool = False,
        min_importance: Optional[int] = None,
        min_confidence: Optional[float] = None,
        is_explicit: Optional[bool] = None,
        created_after: Optional[str] = None,
        created_before: Optional[str] = None,
        updated_after: Optional[str] = None,
        updated_before: Optional[str] = None,
        valid_at: Optional[str] = None,
        sentiment: Optional[str] = None,
        subject_key: Optional[str] = None,
        attribute_key: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> ItemListResult:
        items = search_memories(
            query=query,
            user_code=user_code,
            memory_type=memory_type,
            tags=list(tags or []),
            include_archived=include_archived,
            min_importance=min_importance,
            min_confidence=min_confidence,
            is_explicit=is_explicit,
            created_after=created_after,
            created_before=created_before,
            updated_after=updated_after,
            updated_before=updated_before,
            valid_at=valid_at,
            sentiment=sentiment,
            subject_key=subject_key,
            attribute_key=attribute_key,
            limit=limit,
            offset=offset,
        )
        return ItemListResult(items=items, count=len(items))

    @server.tool(name="search_memory_window", structured_output=True)
    def search_memory_window_tool(
        time_field: MemoryWindowField,
        start_at: Optional[str] = None,
        end_at: Optional[str] = None,
        query: str = "",
        user_code: Optional[str] = None,
        memory_type: Optional[str] = None,
        tags: Optional[list[str]] = None,
        include_archived: bool = False,
        limit: int = 10,
        offset: int = 0,
    ) -> ItemListResult:
        items = search_memories_by_time_range(
            user_code=user_code,
            time_field=time_field,
            start_at=start_at,
            end_at=end_at,
            query=query,
            memory_type=memory_type,
            tags=list(tags or []),
            include_archived=include_archived,
            limit=limit,
            offset=offset,
        )
        return ItemListResult(items=items, count=len(items))

    @server.tool(name="add_memory", structured_output=True)
    def add_memory_tool(
        title: str,
        content: str,
        id: Optional[int] = None,
        user_code: Optional[str] = None,
        memory_type: str = "fact",
        summary: Optional[str] = None,
        tags: Optional[list[str]] = None,
        source_type: str = SOURCE_MANUAL,
        source_ref: Optional[str] = None,
        confidence: float = 0.7,
        importance: int = 5,
        status: str = STATUS_ACTIVE,
        is_explicit: bool = False,
        valid_from: Optional[str] = None,
        valid_to: Optional[str] = None,
        subject_key: Optional[str] = None,
        related_subject_key: Optional[str] = None,
        attribute_key: Optional[str] = None,
        value_text: Optional[str] = None,
        conflict_scope: Optional[str] = None,
    ) -> MemoryMutationResult:
        memory = upsert_memory(
            {
                "id": id,
                "user_code": user_code,
                "memory_type": memory_type,
                "title": title,
                "content": content,
                "summary": summary,
                "tags": list(tags or []),
                "source_type": source_type,
                "source_ref": source_ref,
                "confidence": confidence,
                "importance": importance,
                "status": status,
                "is_explicit": is_explicit,
                "valid_from": valid_from,
                "valid_to": valid_to,
                "subject_key": subject_key,
                "related_subject_key": related_subject_key,
                "attribute_key": attribute_key,
                "value_text": value_text,
                "conflict_scope": conflict_scope,
            }
        )
        return MemoryMutationResult(memory=memory)

    @server.tool(name="delete_memory", structured_output=True)
    def delete_memory_tool(
        id: int, user_code: Optional[str] = None, mode: str = "archive"
    ) -> MemoryMutationResult:
        if mode == "archive":
            memory = archive_memory(id, user_code)
        elif mode == "delete":
            memory = delete_memory_row(id, user_code)
        else:
            raise ValueError("mode must be 'archive' or 'delete'")
        if not memory:
            raise ValueError("memory not found")
        return MemoryMutationResult(memory=memory)

    @server.tool(name="capture_turn", structured_output=True)
    def capture_turn_tool(
        user_text: str,
        assistant_text: str = "",
        session_key: str = DEFAULT_SESSION_KEY,
        user_code: Optional[str] = None,
        topic_hint: Optional[str] = None,
        source_ref: Optional[str] = None,
        consolidate: bool = True,
        sync_context: bool = True,
    ) -> CaptureTurnResult:
        return _execute_capture_turn(
            user_text=user_text,
            assistant_text=assistant_text,
            session_key=session_key,
            user_code=user_code,
            topic_hint=topic_hint,
            source_ref=source_ref,
            consolidate=consolidate,
            sync_context=sync_context,
        )

    @server.tool(name="add_context", structured_output=True)
    def add_context_tool(
        turns: list[dict],
        session_key: str = DEFAULT_SESSION_KEY,
        user_code: Optional[str] = None,
        topic_hint: Optional[str] = None,
        source_ref: Optional[str] = None,
        extract_memory: bool = False,
    ) -> ContextMutationResult:
        context = sync_session_context(
            session_key=session_key,
            turns=turns,
            user_code=user_code,
            topic_hint=topic_hint,
            source_ref=source_ref,
            extract_memory=extract_memory,
        )
        return ContextMutationResult(context=context)

    @server.tool(name="search_recent_dialogue_summaries", structured_output=True)
    def search_recent_dialogue_summaries_tool(
        recent_hours: int = 168,
        query: str = "",
        user_code: Optional[str] = None,
        session_key: Optional[str] = None,
        snapshot_levels: Optional[list[str]] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> ItemListResult:
        items = search_recent_context_summaries(
            user_code=user_code,
            session_key=session_key,
            query=query,
            snapshot_levels=list(snapshot_levels or [SNAPSHOT_SEGMENT, SNAPSHOT_TOPIC]),
            recent_hours=recent_hours,
            limit=limit,
            offset=offset,
        )
        return ItemListResult(items=items, count=len(items))

    @server.tool(name="search_entities", structured_output=True)
    def search_entities_tool(
        query: str = "",
        user_code: Optional[str] = None,
        subject_key: Optional[str] = None,
        include_archived: bool = False,
        limit: int = 10,
        offset: int = 0,
    ) -> ItemListResult:
        items = search_entities(
            query=query,
            user_code=user_code,
            subject_key=subject_key,
            include_archived=include_archived,
            limit=limit,
            offset=offset,
        )
        return ItemListResult(items=items, count=len(items))

    @server.tool(name="search_entity_relationships", structured_output=True)
    def search_entity_relationships_tool(
        query: str = "",
        user_code: Optional[str] = None,
        subject_key: Optional[str] = None,
        include_archived: bool = False,
        limit: int = 10,
        offset: int = 0,
    ) -> ItemListResult:
        items = search_entity_relationships(
            query=query,
            user_code=user_code,
            subject_key=subject_key,
            include_archived=include_archived,
            limit=limit,
            offset=offset,
        )
        return ItemListResult(items=items, count=len(items))

    @server.tool(name="maintain_entity_graph", structured_output=True)
    def maintain_entity_graph_tool(
        user_code: Optional[str] = None,
        force: bool = False,
    ) -> ItemListResult:
        result = rebuild_entity_graph(user_code=user_code, force=force)
        subject_keys = [{"subject_key": value} for value in list(result.get("subject_keys") or [])]
        return ItemListResult(items=subject_keys, count=int(result.get("profile_count") or 0))

    @server.tool(name="update_entity_profile", structured_output=True)
    def update_entity_profile_tool(
        subject_key: str,
        user_code: Optional[str] = None,
        display_name: Optional[str] = None,
        relation_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        result = update_entity_profile(
            subject_key=subject_key,
            user_code=user_code,
            display_name=display_name,
            relation_type=relation_type,
        )
        if not result:
            raise ValueError(f"entity_profile for '{subject_key}' not found or no fields to update")
        return result

    @server.tool(name="delete_entity_profile", structured_output=True)
    def delete_entity_profile_tool(
        subject_key: str,
        user_code: Optional[str] = None,
        cascade_edges: bool = True,
    ) -> Dict[str, Any]:
        deleted = delete_entity_profile(
            subject_key=subject_key,
            user_code=user_code,
            cascade_edges=cascade_edges,
        )
        if not deleted:
            raise ValueError(f"entity_profile for '{subject_key}' not found")
        return {"subject_key": subject_key, "deleted": True, "cascade_edges": cascade_edges}

    @server.tool(name="delete_entity_edge", structured_output=True)
    def delete_entity_edge_tool(
        edge_id: int,
        user_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        deleted = delete_entity_edge(edge_id=edge_id, user_code=user_code)
        if not deleted:
            raise ValueError(f"entity_edge {edge_id} not found")
        return {"edge_id": edge_id, "deleted": True}

    @server.tool(name="search_context", structured_output=True)
    def search_context_tool(
        query: str = "",
        user_code: Optional[str] = None,
        session_key: Optional[str] = None,
        snapshot_level: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> ItemListResult:
        items = search_context_snapshots(
            query=query,
            user_code=user_code,
            session_key=session_key,
            snapshot_level=snapshot_level,
            limit=limit,
            offset=offset,
        )
        return ItemListResult(items=items, count=len(items))

    @server.tool(name="list_domain_values", structured_output=True)
    def list_domain_values_tool(
        domain_name: str,
        include_archived: bool = False,
    ) -> ItemListResult:
        items = list_domain_values(domain_name, include_archived=include_archived)
        return ItemListResult(items=items, count=len(items))

    @server.tool(name="search_domain_candidates", structured_output=True)
    def search_domain_candidates_tool(
        domain_name: Optional[str] = None,
        status: Optional[str] = "pending",
        limit: int = 20,
    ) -> ItemListResult:
        items = list_domain_candidates(domain_name, status=status, limit=limit)
        return ItemListResult(items=items, count=len(items))

    @server.tool(name="approve_domain_candidate", structured_output=True)
    def approve_domain_candidate_tool(
        candidate_id: int,
        canonical_value_key: Optional[str] = None,
    ) -> DomainMutationResult:
        if canonical_value_key:
            result = approve_domain_candidate(
                candidate_id,
                canonical_value_key=canonical_value_key,
            )
        else:
            result = approve_domain_candidate(candidate_id)
        return DomainMutationResult(candidate=result["candidate"], value=result.get("value"))

    @server.tool(name="reject_domain_candidate", structured_output=True)
    def reject_domain_candidate_tool(
        candidate_id: int,
        reason: Optional[str] = None,
    ) -> DomainMutationResult:
        result = reject_domain_candidate(candidate_id, reason=reason)
        return DomainMutationResult(candidate=result["candidate"], value=result.get("value"))

    @server.tool(name="merge_domain_alias", structured_output=True)
    def merge_domain_alias_tool(
        domain_name: str,
        alias_key: str,
        canonical_value_key: str,
        candidate_id: Optional[int] = None,
    ) -> AliasMutationResult:
        result = merge_domain_alias(
            domain_name=domain_name,
            alias_key=alias_key,
            canonical_value_key=canonical_value_key,
            candidate_id=candidate_id,
        )
        return AliasMutationResult(
            alias=result["alias"],
            candidate=result.get("candidate"),
            value=result.get("value"),
        )

    @server.tool(name="maintain_memory_store", structured_output=True)
    def maintain_memory_store_tool(
        user_code: Optional[str] = None,
        limit: int = 200,
        dry_run: bool = False,
        include_archived: bool = False,
        lifecycle_states: Optional[List[str]] = None,
        memory_types: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        auto_archive_stale_days: int = 90,
        auto_resolve_review_days: int = 30,
    ) -> MaintenanceResult:
        result = maintain_memory_store(
            user_code=user_code,
            limit=limit,
            dry_run=dry_run,
            include_archived=include_archived,
            lifecycle_states=lifecycle_states,
            memory_types=memory_types,
            categories=categories,
            auto_archive_stale_days=auto_archive_stale_days,
            auto_resolve_review_days=auto_resolve_review_days,
        )
        return MaintenanceResult(**result)

    @server.tool(name="recall_for_response", structured_output=True)
    def recall_for_response_tool(
        user_message: str,
        draft_response: Optional[str] = None,
        topic_hint: Optional[str] = None,
        user_code: Optional[str] = None,
        memory_limit: int = 3,
        context_limit: int = 3,
        recent_context_limit: int = 2,
        recent_context_hours: int = 168,
        include_cited_sources: bool = False,
    ) -> RecallResult:
        return _build_recall_result(
            user_message=user_message,
            draft_response=draft_response,
            topic_hint=topic_hint,
            user_code=user_code,
            memory_limit=memory_limit,
            context_limit=context_limit,
            recent_context_limit=recent_context_limit,
            recent_context_hours=recent_context_hours,
            include_cited_sources=include_cited_sources,
        )

    @server.tool(name="orchestrate_turn_memory", structured_output=True)
    def orchestrate_turn_memory_tool(
        user_message: str,
        draft_response: Optional[str] = None,
        assistant_text: str = "",
        topic_hint: Optional[str] = None,
        session_key: str = DEFAULT_SESSION_KEY,
        user_code: Optional[str] = None,
        source_ref: Optional[str] = None,
        memory_limit: int = 3,
        context_limit: int = 3,
        recent_context_limit: int = 2,
        recent_context_hours: int = 168,
        consolidate: bool = True,
        sync_context: bool = True,
        capture_after_response: bool = False,
        sync_every_n_turns: int = 0,  # 0=每次都同步，N>0=每 N 轮同步一次
    ) -> TurnOrchestrationResult:
        recall = _build_recall_result(
            user_message=user_message,
            draft_response=draft_response,
            topic_hint=topic_hint,
            user_code=user_code,
            memory_limit=memory_limit,
            context_limit=context_limit,
            recent_context_limit=recent_context_limit,
            recent_context_hours=recent_context_hours,
        )
        should_capture = bool(user_message.strip() or assistant_text.strip())
        capture_plan = {
            "tool": "capture_turn",
            "user_text": user_message,
            "assistant_text": assistant_text,
            "session_key": session_key,
            "topic_hint": topic_hint,
            "source_ref": source_ref,
            "consolidate": consolidate,
            "sync_context": sync_context,
            "should_capture": should_capture,
        }
        executed_capture = None
        # B2: determine whether to sync this turn
        if sync_every_n_turns > 0:
            turn_count = _increment_turn_count(session_key)
            should_sync = (turn_count % sync_every_n_turns == 0)
        else:
            should_sync = sync_context
        if should_capture and capture_after_response and assistant_text.strip():
            executed_capture = _execute_capture_turn(
                user_text=user_message,
                assistant_text=assistant_text,
                session_key=session_key,
                user_code=user_code,
                topic_hint=topic_hint,
                source_ref=source_ref,
                consolidate=consolidate,
                sync_context=should_sync,
            ).model_dump()
        return TurnOrchestrationResult(
            recall=recall.model_dump(),
            should_capture=should_capture,
            capture_plan=capture_plan,
            executed_capture=executed_capture,
            recommended_sequence=["recall_for_response", "answer_user", "capture_turn"],
        )

    @server.tool(name="merge_duplicate_memories", structured_output=True)
    def merge_duplicate_memories_tool(
        user_code: Optional[str] = None,
        similarity_threshold: float = 0.92,
        dry_run: bool = False,
        limit: int = 50,
    ) -> MergeResult:
        result = merge_duplicate_memories(
            user_code=user_code,
            similarity_threshold=similarity_threshold,
            dry_run=dry_run,
            limit=limit,
        )
        return MergeResult(**result)

    @server.tool(name="get_stale_memories_for_challenge", structured_output=True)
    def get_stale_memories_for_challenge_tool(
        user_code: Optional[str] = None,
        limit: int = 5,
        min_days_since_recall: int = 30,
        memory_types: Optional[List[str]] = None,
    ) -> ItemListResult:
        items = get_stale_for_challenge(
            user_code=user_code,
            limit=limit,
            min_days_since_recall=min_days_since_recall,
            memory_types=memory_types,
        )
        return ItemListResult(items=items, count=len(items))

    @server.tool(name="list_evidence", structured_output=True)
    def list_evidence_tool(
        user_code: Optional[str] = None,
        conflict_scope: Optional[str] = None,
        limit: int = 20,
    ) -> ItemListResult:
        """列出积累中的证据信号（memory_signal 表）。"""
        items = list_evidence(user_code=user_code, conflict_scope=conflict_scope, limit=limit)
        return ItemListResult(items=items, count=len(items))

    @server.tool(name="fetch_source_turns", structured_output=True)
    def fetch_source_turns_tool(
        source_refs: List[str],
    ) -> Dict[str, Any]:
        """查询记忆来源对话轮次。source_refs 格式为 ['session_key:turn_id', ...]。"""
        result = fetch_source_turns(source_refs)
        return {"items": list(result.values()), "count": len(result), "ref_map": result}

    @server.tool(name="get_memory_timeline", structured_output=True)
    async def get_memory_timeline_tool(
        user_code: Optional[str] = None,
        memory_id: Optional[int] = None,
        subject_key: Optional[str] = None,
        attribute_key: Optional[str] = None,
        limit: int = 20,
    ) -> ItemListResult:
        items = get_memory_timeline(
            user_code=user_code,
            memory_id=memory_id,
            subject_key=subject_key,
            attribute_key=attribute_key,
            limit=limit,
        )
        return ItemListResult(items=items, count=len(items))

    @server.tool(name="export_memories", structured_output=True)
    async def export_memories_tool(
        user_code: Optional[str] = None,
        sensitivity_levels: Optional[List[str]] = None,
        format: str = "json",
        include_archived: bool = False,
        memory_types: Optional[List[str]] = None,
    ) -> ExportResult:
        result = export_memory_records(
            user_code=user_code,
            sensitivity_levels=sensitivity_levels,
            format=format,
            include_archived=include_archived,
            memory_types=memory_types,
        )
        return ExportResult(**result)

    @server.tool(name="generate_memory_report", structured_output=True)
    async def generate_memory_report_tool(
        user_code: Optional[str] = None,
        period_days: int = 30,
    ) -> MemoryReport:
        result = generate_memory_report(user_code=user_code, period_days=period_days)
        return MemoryReport(**result)

    @server.tool(name="batch_ingest_turns", structured_output=True)
    async def batch_ingest_turns_tool(
        turns: List[Dict[str, Any]],
        session_key: str = "default",
        user_code: Optional[str] = None,
        topic_hint: Optional[str] = None,
        analyze: bool = True,
        rate_limit_ms: int = 500,
    ) -> IngestResult:
        from service.capture_cycle import _resolve_user as _cc_resolve_user
        resolved_user = _cc_resolve_user(user_code)
        pairs, failed = _pair_turns(turns)
        ingested_turns = 0
        created_memories = 0
        loop = asyncio.get_running_loop()
        for user_turn, assistant_turn in pairs:
            result = await loop.run_in_executor(
                None,
                lambda u=user_turn, a=assistant_turn: run_capture_cycle(
                    user_text=str(u.get("content") or ""),
                    assistant_text=str(a.get("content") or ""),
                    user_code=resolved_user,
                    session_key=session_key,
                    consolidate=False,
                ),
            )
            ingested_turns += 1
            created_memories += int(result.get("persisted_count") or 0)
            if rate_limit_ms > 0:
                await asyncio.sleep(rate_limit_ms / 1000.0)
        return IngestResult(
            ingested_turns=ingested_turns,
            created_memories=created_memories,
            failed_turns=failed,
        )

    @server.tool(name="list_review_candidates", structured_output=True)
    def list_review_candidates_tool(
        user_code: Optional[str] = None,
        limit: int = 20,
    ) -> ReviewCandidateList:
        rows = list_review_candidates(user_code=user_code, limit=limit)
        return ReviewCandidateList(
            candidates=[ReviewCandidate(**r) for r in rows],
            total=len(rows),
        )

    @server.tool(name="list_working_memories", structured_output=True)
    def list_working_memories_tool(
        user_code: Optional[str] = None,
        session_key: Optional[str] = None,
        limit: int = 20,
    ) -> WorkingMemoryList:
        rows = list_working_memories(
            user_code=user_code, session_key=session_key, limit=limit
        )
        return WorkingMemoryList(
            memories=[WorkingMemory(**r) for r in rows],
            total=len(rows),
        )

    @server.tool(name="approve_review_candidate", structured_output=True)
    def approve_review_candidate_tool(
        candidate_id: int,
        user_code: Optional[str] = None,
    ) -> MemoryMutationResult:
        result = approve_review_candidate(candidate_id=candidate_id, user_code=user_code)
        if not result:
            raise ValueError(f"candidate {candidate_id} not found or already processed")
        return MemoryMutationResult(memory=result["memory"])

    @server.tool(name="reject_review_candidate", structured_output=True)
    def reject_review_candidate_tool(
        candidate_id: int,
        user_code: Optional[str] = None,
    ) -> ReviewCandidate:
        result = reject_review_candidate(candidate_id=candidate_id, user_code=user_code)
        if not result:
            raise ValueError(f"candidate {candidate_id} not found or already processed")
        return ReviewCandidate(**result)

    @server.tool(name="submit_challenge_answer", structured_output=True)
    def submit_challenge_answer_tool(
        memory_id: int,
        confirmed: bool,
        answer: Optional[str] = None,
        user_code: Optional[str] = None,
    ) -> MemoryMutationResult:
        result = submit_challenge_answer(
            memory_id=memory_id,
            user_code=user_code,
            confirmed=confirmed,
            answer=answer,
        )
        if "error" in result:
            raise ValueError(result["error"])
        return MemoryMutationResult(**result)

    @server.tool(name="revert_memory_to_version", structured_output=True)
    def revert_memory_to_version_tool(
        memory_id: int,
        target_version_id: int,
        user_code: Optional[str] = None,
    ) -> MemoryMutationResult:
        result = revert_memory_to_version(
            memory_id=memory_id,
            target_version_id=target_version_id,
            user_code=user_code,
        )
        if "error" in result:
            raise ValueError(result["error"])
        return MemoryMutationResult(**result)

    return server


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "streamable-http", "sse"], default="stdio")
    parser.add_argument("--host", default=_service_host())
    parser.add_argument("--port", type=int, default=_service_port())
    parser.add_argument("--path", default="/mcp")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    server = create_server(host=args.host, port=args.port, streamable_http_path=args.path)
    server.run(transport=args.transport)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
