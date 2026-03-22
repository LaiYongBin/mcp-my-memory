"""Conversation-end memory capture and consolidation."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional

from service.constants import (
    ACTION_LONG_TERM,
    ACTION_REVIEW,
    ACTION_WORKING_MEMORY,
    CONFLICT_COEXIST,
    CONFLICT_REPLACE,
    CONFLICT_REVIEW,
    EVIDENCE_EXPLICIT,
    EVENT_TURN,
    ROLE_ASSISTANT,
    ROLE_USER,
    SOURCE_ANALYSIS,
    SOURCE_CONSOLIDATION,
    STATUS_ACTIVE,
    STATUS_ARCHIVED,
    STATUS_PENDING,
    TIME_LONG_TERM,
)
from service.analyzer import analyze_turn, mark_event_analyzed, save_analysis_results
from service.db import get_conn, get_settings
from service.evidence import accumulate_evidence, evidence_supports_promotion, mark_evidence_promoted, promoted_confidence
from service.extraction import extract_candidates, extract_review_candidates, should_auto_persist
from service.memory_ops import archive_memory, list_memories_by_conflict_scope, save_review_candidate, upsert_memory


TEMPORAL_HINTS = [
    "今天",
    "这周",
    "本周",
    "最近",
    "目前",
    "当前",
    "暂时",
    "先",
    "现在",
    "这两天",
    "今晚",
    "明天",
    "下周",
    "本月",
]

WORKING_HINTS = [
    "在做",
    "正在",
    "处理",
    "排查",
    "推进",
    "优先",
    "先做",
    "先看",
    "准备",
    "计划",
    "目标",
    "本次",
    "这次",
]


def _resolve_user(user_code: Optional[str]) -> str:
    return user_code or str(get_settings()["memory_user"])


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _memory_key(text: str) -> str:
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "", text.lower())
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()[:16]


def _looks_short_term(text: str) -> bool:
    cleaned = _clean_text(text)
    return any(token in cleaned for token in TEMPORAL_HINTS + WORKING_HINTS)


def _working_importance(text: str) -> int:
    cleaned = _clean_text(text)
    if any(token in cleaned for token in ["优先", "目标", "排查", "正在", "推进"]):
        return 5
    return 4


def record_conversation_event(
    *,
    user_code: str,
    session_key: str,
    role: str,
    content: str,
    source_ref: Optional[str] = None,
    event_type: str = EVENT_TURN,
) -> Optional[Dict[str, Any]]:
    cleaned = _clean_text(content)
    if not cleaned:
        return None
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO conversation_turn (
                user_code, session_key, event_type, role, content, source_ref
            ) VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, user_code, session_key, event_type, role, content, source_ref, created_at
            """,
            (user_code, session_key, event_type, role, cleaned, source_ref),
        )
        row = cur.fetchone()
        conn.commit()
        return dict(row) if row else None


def upsert_working_memory(
    *,
    user_code: str,
    session_key: str,
    summary: str,
    source_text: str,
    importance: int,
    expires_in_days: int = 7,
) -> Dict[str, Any]:
    memory_key = _memory_key(summary)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM session_state
            WHERE user_code = %s
              AND memory_key = %s
              AND status = %s
              AND (expires_at IS NULL OR expires_at > now())
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (user_code, memory_key, STATUS_ACTIVE),
        )
        existing = cur.fetchone()
        if existing:
            cur.execute(
                """
                UPDATE session_state
                SET session_key = %s,
                    summary = %s,
                    importance = GREATEST(importance, %s),
                    expires_at = now() + (%s || ' days')::interval,
                    source_text = %s,
                    updated_at = now(),
                    status = %s
                WHERE id = %s
                RETURNING id, user_code, session_key, memory_key, summary, importance,
                          expires_at, source_text, status, created_at, updated_at
                """,
                (session_key, summary, importance, expires_in_days, source_text, STATUS_ACTIVE, existing["id"]),
            )
        else:
            cur.execute(
                """
                INSERT INTO session_state (
                    user_code, session_key, memory_key, summary, importance,
                    expires_at, source_text, status
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    now() + (%s || ' days')::interval, %s, %s
                )
                RETURNING id, user_code, session_key, memory_key, summary, importance,
                          expires_at, source_text, status, created_at, updated_at
                """,
                (user_code, session_key, memory_key, summary, importance, expires_in_days, source_text, STATUS_ACTIVE),
            )
        row = cur.fetchone()
        conn.commit()
        return dict(row)


def list_working_memories(
    *, user_code: Optional[str] = None, session_key: Optional[str] = None, limit: int = 20
) -> List[Dict[str, Any]]:
    resolved_user = _resolve_user(user_code)
    conditions = ["user_code = %s", "status = %s"]
    params: List[Any] = [resolved_user, STATUS_ACTIVE]
    if session_key:
        conditions.append("session_key = %s")
        params.append(session_key)
    where_sql = " AND ".join(conditions)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id, user_code, session_key, memory_key, summary, importance,
                   expires_at, source_text, status, created_at, updated_at
            FROM session_state
            WHERE {where_sql}
            ORDER BY importance DESC, updated_at DESC
            LIMIT %s
            """,
            params + [limit],
        )
        return [dict(row) for row in cur.fetchall()]


def build_working_memory_candidates(user_text: str, assistant_text: str = "") -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    cleaned_user = _clean_text(user_text)
    if cleaned_user and _looks_short_term(cleaned_user):
        candidates.append(
            {
                "summary": cleaned_user[:240],
                "source_text": cleaned_user,
                "importance": _working_importance(cleaned_user),
            }
        )
    cleaned_assistant = _clean_text(assistant_text)
    if cleaned_assistant and any(token in cleaned_assistant for token in ["下一步", "接下来", "先", "会继续"]):
        candidates.append(
            {
                "summary": cleaned_assistant[:240],
                "source_text": cleaned_assistant,
                "importance": 3,
            }
        )
    return candidates


def consolidate_working_memories(
    *, user_code: Optional[str] = None, session_key: Optional[str] = None
) -> Dict[str, Any]:
    resolved_user = _resolve_user(user_code)
    archived = 0
    promoted: List[Dict[str, Any]] = []
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE session_state
            SET status = %s, updated_at = now()
            WHERE user_code = %s
              AND status = %s
              AND expires_at IS NOT NULL
              AND expires_at <= now()
            RETURNING id
            """,
            (STATUS_ARCHIVED, resolved_user, STATUS_ACTIVE),
        )
        archived = len(cur.fetchall())

        conditions = ["user_code = %s", "status = %s"]
        params: List[Any] = [resolved_user, STATUS_ACTIVE]
        if session_key:
            conditions.append("session_key = %s")
            params.append(session_key)
        where_sql = " AND ".join(conditions)
        cur.execute(
            f"""
            SELECT memory_key,
                   max(summary) AS summary,
                   max(source_text) AS source_text,
                   max(importance) AS importance,
                   max(id) AS id,
                   count(*) AS occurrence_count
            FROM session_state
            WHERE {where_sql}
              AND memory_key IS NOT NULL
            GROUP BY memory_key
            ORDER BY count(*) DESC, max(updated_at) DESC
            """,
            params,
        )
        rows = [dict(row) for row in cur.fetchall()]
        conn.commit()

    for row in rows:
        summary = str(row.get("summary") or "").strip()
        if not summary:
            continue
        content_hash = hashlib.md5(summary.encode()).hexdigest()[:8]
        pseudo_item = {
            "subject": "user",
            "attribute": "working_memory",
            "value": summary,
            "claim": str(row.get("source_text") or summary),
            "category": "current_goal",
            "evidence_type": "observed",
            "time_scope": "short_term",
            "action": "long_term",
            "confidence": 0.6,
            "conflict_scope": f"user.working_memory.{content_hash}",
            "tags": [],
        }
        evidence = accumulate_evidence(user_code=resolved_user, item=pseudo_item)
        if evidence and evidence_supports_promotion(pseudo_item, evidence):
            upsert_memory(
                {
                    "user_code": resolved_user,
                    "memory_type": "fact",
                    "title": summary[:80],
                    "content": summary,
                    "summary": summary[:240],
                    "tags": ["working-memory", "auto-consolidated"],
                    "source_type": SOURCE_CONSOLIDATION,
                    "confidence": promoted_confidence(pseudo_item, evidence),
                    "importance": int(row.get("importance") or 4),
                    "status": STATUS_ACTIVE,
                    "is_explicit": False,
                    "subject_key": "user",
                    "attribute_key": "working_memory",
                    "value_text": summary[:500],
                }
            )
            promoted.append({"summary": summary})
            # 标记已提升
            with get_conn() as conn2, conn2.cursor() as cur2:
                cur2.execute(
                    "UPDATE session_state SET status = %s WHERE id = %s",
                    (STATUS_ARCHIVED, int(row["id"])),
                )
                conn2.commit()
        # 不满足则保留在 session_state，等待下次积累

    return {
        "archived_count": archived,
        "promoted": promoted,
        "promoted_count": len(promoted),
    }


def _build_memory_payload_from_analysis(item: Dict[str, Any], user_code: str) -> Dict[str, Any]:
    category = str(item.get("category") or SOURCE_ANALYSIS)
    attribute = str(item.get("attribute") or "memory")
    value = str(item.get("value") or item.get("claim") or "").strip()
    if category == "preference":
        memory_type = "preference"
    elif category == "relationship":
        memory_type = "relationship"
    elif category == "self_description":
        memory_type = "fact"
    else:
        memory_type = "context"
    return {
        "user_code": user_code,
        "memory_type": memory_type,
        "category": category,
        "title": f"{attribute}: {value[:60]}",
        "content": str(item.get("claim") or value),
        "summary": value[:240],
        "tags": list(dict.fromkeys(list(item.get("tags") or []) + ["analysis"])),
        "source_type": SOURCE_ANALYSIS,
        "confidence": float(item.get("confidence") or 0.5),
        "importance": 5 if item.get("time_scope") == TIME_LONG_TERM else 4,
        "status": STATUS_ACTIVE,
        "is_explicit": item.get("evidence_type") == EVIDENCE_EXPLICIT,
        "subject_key": item.get("subject"),
        "related_subject_key": item.get("related_subject"),
        "attribute_key": item.get("attribute"),
        "value_text": value,
        "conflict_scope": item.get("conflict_scope"),
    }


def resolve_analysis_memory(item: Dict[str, Any], user_code: str) -> Dict[str, Any]:
    payload = _build_memory_payload_from_analysis(item, user_code)
    conflict_scope = str(item.get("conflict_scope") or "").strip()
    conflict_mode = str(item.get("conflict_mode") or CONFLICT_COEXIST)
    existing = (
        list_memories_by_conflict_scope(user_code=user_code, conflict_scope=conflict_scope)
        if conflict_scope
        else []
    )
    exact_match = next(
        (
            row
            for row in existing
            if str(row.get("value_text") or row.get("content") or "").strip() == payload["value_text"]
        ),
        None,
    )
    if exact_match:
        payload["id"] = int(exact_match["id"])
        return {"memory": upsert_memory(payload), "resolution": "updated-existing"}

    if existing and conflict_mode == CONFLICT_REPLACE:
        archived = []
        for row in existing:
            archived_row = archive_memory(int(row["id"]), user_code)
            if archived_row:
                archived.append(archived_row)
        return {
            "memory": upsert_memory(payload),
            "resolution": "replaced-conflicting",
            "archived": archived,
        }

    if existing and conflict_mode == CONFLICT_REVIEW:
        return {"memory": None, "resolution": "needs-review", "existing": existing}

    return {"memory": upsert_memory(payload), "resolution": "inserted-new"}


def run_capture_cycle(
    *,
    user_text: str,
    assistant_text: str = "",
    user_code: Optional[str] = None,
    session_key: str = "default",
    source_ref: Optional[str] = None,
    consolidate: bool = True,
) -> Dict[str, Any]:
    resolved_user = _resolve_user(user_code)
    events = []
    assistant_event = None
    user_event = record_conversation_event(
        user_code=resolved_user,
        session_key=session_key,
        role=ROLE_USER,
        content=user_text,
        source_ref=source_ref,
    )
    if user_event:
        events.append(user_event)
    if assistant_text.strip():
        assistant_event = record_conversation_event(
            user_code=resolved_user,
            session_key=session_key,
            role=ROLE_ASSISTANT,
            content=assistant_text,
            source_ref=source_ref,
        )
    if assistant_event:
        events.append(assistant_event)

    analysis_candidates = analyze_turn(
        user_text=user_text,
        assistant_text=assistant_text,
        user_code=resolved_user,
        session_key=session_key,
    )
    analysis_results = save_analysis_results(
        user_code=resolved_user,
        session_key=session_key,
        source_event_id=int(user_event["id"]) if user_event else None,
        items=analysis_candidates,
    )
    mark_event_analyzed([int(event["id"]) for event in events if event.get("id")])

    persisted = []
    pending_candidates = []
    review_items = []
    evidence_items = []
    for item in analysis_results:
        action = item.get("action")
        claim = str(item.get("claim") or "").strip()
        category = str(item.get("category") or "analysis")
        confidence = float(item.get("confidence") or 0.5)
        tags = list(item.get("tags") or [])
        evidence = None
        if action == ACTION_LONG_TERM and claim:
            evidence = accumulate_evidence(user_code=resolved_user, item=item)
            if evidence:
                evidence_items.append(evidence)
            if evidence_supports_promotion(item, evidence):
                promoted_item = item.copy()
                promoted_item["confidence"] = promoted_confidence(item, evidence)
                resolved = resolve_analysis_memory(promoted_item, resolved_user)
                memory_payload = resolved.get("memory")
                if memory_payload:
                    persisted.append(resolved)
                    memory_id = memory_payload.get("id") if isinstance(memory_payload, dict) else None
                    if evidence and memory_id:
                        mark_evidence_promoted(int(evidence["id"]), int(memory_id))
                elif resolved.get("resolution") == "needs-review":
                    review_items.append(
                        save_review_candidate(
                            user_code=resolved_user,
                            source_text=user_text,
                            candidate={
                                "title": "待确认候选: " + claim[:60],
                                "content": claim,
                                "memory_type": "context",
                                "reason": "analysis-conflict-review:" + category,
                                "confidence": confidence,
                                "tags": list(dict.fromkeys(tags + ["analysis-review"])),
                                "status": STATUS_PENDING,
                            },
                        )
                    )
        elif action == ACTION_REVIEW and claim:
            evidence = accumulate_evidence(user_code=resolved_user, item=item)
            if evidence:
                evidence_items.append(evidence)
            review_items.append(
                save_review_candidate(
                    user_code=resolved_user,
                    source_text=user_text,
                    candidate={
                        "title": "待确认候选: " + claim[:60],
                        "content": claim,
                        "memory_type": "context",
                        "reason": "analysis-review:" + category,
                        "confidence": confidence,
                        "tags": list(dict.fromkeys(tags + ["analysis-review"])),
                        "status": STATUS_PENDING,
                    },
                )
            )

    heuristic_candidates = extract_candidates(user_text)
    for candidate in heuristic_candidates:
        payload = candidate.copy()
        payload["user_code"] = resolved_user
        if should_auto_persist(candidate):
            persisted.append(upsert_memory(payload))
        else:
            pending_candidates.append(candidate)

    for candidate in extract_review_candidates(user_text):
        review_items.append(
            save_review_candidate(user_code=resolved_user, source_text=user_text, candidate=candidate)
        )

    working_items: List[Dict[str, Any]] = []
    for item in analysis_results:
        if item.get("action") != ACTION_WORKING_MEMORY:
            continue
        claim = str(item.get("claim") or "").strip()
        if not claim:
            continue
        tags = list(item.get("tags") or [])
        working_items.append(
            upsert_working_memory(
                user_code=resolved_user,
                session_key=session_key,
                summary=claim[:240],
                source_text=claim,
                importance=5 if "coding" in tags or "short-term" in tags else 4,
            )
        )
    for candidate in build_working_memory_candidates(user_text, assistant_text):
        working_items.append(
            upsert_working_memory(
                user_code=resolved_user,
                session_key=session_key,
                summary=candidate["summary"],
                source_text=candidate["source_text"],
                importance=int(candidate["importance"]),
            )
        )

    consolidation = None
    if consolidate:
        consolidation = consolidate_working_memories(user_code=resolved_user, session_key=session_key)

    return {
        "events": events,
        "event_count": len(events),
        "analysis_results": analysis_results,
        "analysis_result_count": len(analysis_results),
        "persisted": persisted,
        "persisted_count": len(persisted),
        "candidates": pending_candidates,
        "candidate_count": len(pending_candidates),
        "working_memory": working_items,
        "working_memory_count": len(working_items),
        "review_candidates": review_items,
        "review_candidate_count": len(review_items),
        "evidence": evidence_items,
        "evidence_count": len(evidence_items),
        "consolidation": consolidation,
    }
