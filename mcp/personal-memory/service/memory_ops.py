"""Core PostgreSQL memory operations."""

import json
import logging
from typing import Any, Dict, List, Optional

from psycopg.types.json import Json

from service.constants import (
    HYBRID_SEARCH_ENABLED,
    SOURCE_CONVERSATION,
    SOURCE_MANUAL,
    SOURCE_REVIEW_APPROVED,
    STATUS_ACTIVE,
    STATUS_APPROVED,
    STATUS_ARCHIVED,
    STATUS_DELETED,
    STATUS_PENDING,
    STATUS_REJECTED,
)
from service.db import get_conn, get_settings
from service.domain_registry import (
    DOMAIN_ATTRIBUTE_KEY,
    DOMAIN_CATEGORY,
    DOMAIN_MEMORY_TYPE,
    DOMAIN_SOURCE_TYPE,
    resolve_lookup_value,
    resolve_taxonomy_value,
)
from service.embeddings import embeddings_enabled, generate_embedding, refresh_memory_embedding, vector_search
from pgvector.psycopg import Vector
from service.entity_graph import refresh_entity_graph_for_subject, sync_entity_graph_for_memory
from service.memory_governance import apply_memory_governance, derive_lifecycle_state


MEMORY_SELECT_COLUMNS = """
    id, user_code, memory_type, category, title, content, summary, tags,
    source_type, source_ref, confidence, importance, status,
    is_explicit, supersedes_id, conflict_with_id,
    valid_from, valid_to, subject_key, related_subject_key, attribute_key, value_text,
    conflict_scope, sensitivity_level, disclosure_policy, lifecycle_state,
    stability_score, recall_count, last_recalled_at, created_at, updated_at, deleted_at
"""

TIME_FIELD_SQL = {
    "created_at": "created_at",
    "updated_at": "updated_at",
    "valid_from": "valid_from",
    "valid_to": "valid_to",
}


logger = logging.getLogger(__name__)


def _resolve_user(user_code: Optional[str]) -> str:
    return user_code or str(get_settings()["memory_user"])


def _normalize_memory_taxonomy(
    *,
    memory_type: Optional[str],
    category: Optional[str],
    source_type: Optional[str],
    attribute_key: Optional[str],
    source_ref: Optional[str],
) -> Dict[str, str]:
    resolved_memory_type = resolve_taxonomy_value(
        DOMAIN_MEMORY_TYPE,
        memory_type or "fact",
        source="memory_write",
        source_ref=source_ref,
        reason="normalize memory_type during memory write",
    )
    resolved_source_type = resolve_taxonomy_value(
        DOMAIN_SOURCE_TYPE,
        source_type or SOURCE_MANUAL,
        source="memory_write",
        source_ref=source_ref,
        reason="normalize source_type during memory write",
    )
    resolved_category = resolve_taxonomy_value(
        DOMAIN_CATEGORY,
        category or memory_type or "context",
        source="memory_write",
        source_ref=source_ref,
        reason="normalize category during memory write",
    )
    resolved_attribute = None
    if attribute_key:
        resolved_attribute = resolve_taxonomy_value(
            DOMAIN_ATTRIBUTE_KEY,
            attribute_key,
            source="memory_write",
            source_ref=source_ref,
            reason="normalize attribute_key during memory write",
        )
    return {
        "memory_type": str(resolved_memory_type["value_key"]),
        "source_type": str(resolved_source_type["value_key"]),
        "category": str(resolved_category["value_key"]),
        "attribute_key": str(resolved_attribute["value_key"]) if resolved_attribute else "",
    }


def get_memory(memory_id: int, user_code: Optional[str] = None) -> Optional[Dict[str, Any]]:
    resolved_user = _resolve_user(user_code)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                """
            + MEMORY_SELECT_COLUMNS
            + """
            FROM memory_record
            WHERE id = %s AND user_code = %s
            """,
            (memory_id, resolved_user),
        )
        row = cur.fetchone()
        return apply_memory_governance(dict(row)) if row else None


def find_existing_memory(
    *, user_code: str, memory_type: str, title: str, content: str
) -> Optional[Dict[str, Any]]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                """
            + MEMORY_SELECT_COLUMNS
            + """
            FROM memory_record
            WHERE user_code = %s
              AND memory_type = %s
              AND title = %s
              AND content = %s
              AND deleted_at IS NULL
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (user_code, memory_type, title, content),
        )
        row = cur.fetchone()
        return apply_memory_governance(dict(row)) if row else None


def list_memories_by_conflict_scope(
    *, user_code: str, conflict_scope: str, include_archived: bool = False
) -> List[Dict[str, Any]]:
    conditions = ["user_code = %s", "conflict_scope = %s", "deleted_at IS NULL"]
    params: List[Any] = [user_code, conflict_scope]
    if not include_archived:
        conditions.append(f"status = '{STATUS_ACTIVE}'")
    where_sql = " AND ".join(conditions)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {MEMORY_SELECT_COLUMNS}
            FROM memory_record
            WHERE {where_sql}
            ORDER BY updated_at DESC, id DESC
            """,
            params,
        )
        return [apply_memory_governance(dict(row)) for row in cur.fetchall()]


def save_review_candidate(
    *, user_code: str, source_text: str, candidate: Dict[str, Any]
) -> Dict[str, Any]:
    normalized_memory_type = resolve_taxonomy_value(
        DOMAIN_MEMORY_TYPE,
        candidate.get("memory_type") or "fact",
        source="review_candidate",
        source_ref=None,
        reason="normalize memory_type for review candidate",
        confidence=float(candidate.get("confidence", 0.35) or 0.35),
    )
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO memory_candidate (
                user_code, source_text, title, content, memory_type, reason,
                confidence, status, tags
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, user_code, source_text, title, content, memory_type, reason,
                      confidence, status, tags, created_at, updated_at
            """,
            (
                user_code,
                source_text,
                candidate["title"],
                candidate["content"],
                normalized_memory_type["value_key"],
                candidate["reason"],
                candidate.get("confidence", 0.35),
                candidate.get("status", STATUS_PENDING),
                Json(candidate.get("tags") or []),
            ),
        )
        row = cur.fetchone()
        conn.commit()
        return dict(row)


def list_review_candidates(user_code: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    resolved_user = _resolve_user(user_code)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, user_code, source_text, title, content, memory_type, reason,
                   confidence, status, tags, created_at, updated_at
            FROM memory_candidate
            WHERE user_code = %s AND status = %s
            ORDER BY updated_at DESC, id DESC
            LIMIT %s
            """,
            (resolved_user, STATUS_PENDING, limit),
        )
        return [dict(row) for row in cur.fetchall()]


def get_review_candidate(candidate_id: int, user_code: Optional[str] = None) -> Optional[Dict[str, Any]]:
    resolved_user = _resolve_user(user_code)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, user_code, source_text, title, content, memory_type, reason,
                   confidence, status, tags, created_at, updated_at
            FROM memory_candidate
            WHERE id = %s AND user_code = %s
            """,
            (candidate_id, resolved_user),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def reject_review_candidate(candidate_id: int, user_code: Optional[str] = None) -> Optional[Dict[str, Any]]:
    resolved_user = _resolve_user(user_code)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE memory_candidate
            SET status = %s, updated_at = now()
            WHERE id = %s AND user_code = %s AND status = %s
            RETURNING id, user_code, source_text, title, content, memory_type, reason,
                      confidence, status, tags, created_at, updated_at
            """,
            (STATUS_REJECTED, candidate_id, resolved_user, STATUS_PENDING),
        )
        row = cur.fetchone()
        conn.commit()
        return dict(row) if row else None


def approve_review_candidate(candidate_id: int, user_code: Optional[str] = None) -> Optional[Dict[str, Any]]:
    resolved_user = _resolve_user(user_code)
    candidate = get_review_candidate(candidate_id, resolved_user)
    if not candidate or candidate.get("status") != STATUS_PENDING:
        return None

    memory = upsert_memory(
        {
            "user_code": resolved_user,
            "memory_type": candidate["memory_type"],
            "title": candidate["title"].replace("待确认候选: ", "确认记忆: ", 1),
            "content": candidate["content"],
            "summary": candidate["content"][:240],
            "tags": candidate.get("tags") or [],
            "source_type": SOURCE_REVIEW_APPROVED,
            "confidence": float(candidate.get("confidence") or 0.5),
            "importance": 6,
            "status": STATUS_ACTIVE,
            "is_explicit": True,
        }
    )

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE memory_candidate
            SET status = %s, updated_at = now()
            WHERE id = %s AND user_code = %s
            """,
            (STATUS_APPROVED, candidate_id, resolved_user),
        )
        conn.commit()

    return {
        "candidate": get_review_candidate(candidate_id, resolved_user),
        "memory": memory,
    }


def search_memories(
    *,
    query: str = "",
    user_code: Optional[str] = None,
    memory_type: Optional[str] = None,
    tags: Optional[List[str]] = None,
    include_archived: bool = False,
    min_importance: Optional[int] = None,
    min_confidence: Optional[float] = None,
    is_explicit: Optional[bool] = None,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
    updated_after: Optional[str] = None,
    updated_before: Optional[str] = None,
    valid_at: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    resolved_user = _resolve_user(user_code)
    query_vec: Optional[List[float]] = None
    vector_scores = {}
    if query.strip() and embeddings_enabled():
        try:
            query_vec = generate_embedding(query.strip())
            if query_vec is not None:
                for row in vector_search(query.strip(), resolved_user, limit=limit):
                    vector_scores[int(row["memory_id"])] = float(row["vector_score"])
        except Exception as exc:
            logger.warning("vector search unavailable, falling back to lexical search: %s", exc)

    if HYBRID_SEARCH_ENABLED and query_vec is not None:
        return _search_memories_hybrid(
            user_code=resolved_user,
            query_text=query.strip(),
            query_vec=query_vec,
            limit=limit,
            memory_type=memory_type,
            tags=tags,
            include_archived=include_archived,
        )

    tags = tags or []
    conditions = ["user_code = %s", "deleted_at IS NULL"]
    where_params: List[Any] = [resolved_user]
    select_params: List[Any] = []
    if not include_archived:
        conditions.append(f"status = '{STATUS_ACTIVE}'")
    if memory_type:
        conditions.append("memory_type = %s")
        where_params.append(resolve_lookup_value(DOMAIN_MEMORY_TYPE, memory_type) or memory_type)
    if tags:
        conditions.append("tags ?| %s")
        where_params.append(tags)
    if min_importance is not None:
        conditions.append("importance >= %s")
        where_params.append(min_importance)
    if min_confidence is not None:
        conditions.append("confidence >= %s")
        where_params.append(min_confidence)
    if is_explicit is not None:
        conditions.append("is_explicit = %s")
        where_params.append(is_explicit)
    if created_after:
        conditions.append("created_at >= %s")
        where_params.append(created_after)
    if created_before:
        conditions.append("created_at <= %s")
        where_params.append(created_before)
    if updated_after:
        conditions.append("updated_at >= %s")
        where_params.append(updated_after)
    if updated_before:
        conditions.append("updated_at <= %s")
        where_params.append(updated_before)
    if valid_at:
        conditions.append("(valid_from IS NULL OR valid_from <= %s)")
        conditions.append("(valid_to IS NULL OR valid_to >= %s)")
        where_params.extend([valid_at, valid_at])

    rank_sql = "0::float AS rank_score"
    if query.strip():
        conditions.append(
            """
            (
                search_vector @@ websearch_to_tsquery('simple', %s)
                OR title ILIKE %s
                OR content ILIKE %s
                OR coalesce(summary, '') ILIKE %s
            )
            """
        )
        where_params.append(query.strip())
        like_query = "%" + query.strip() + "%"
        where_params.extend([like_query, like_query, like_query])
        rank_sql = (
            """
            CASE
                WHEN search_vector @@ websearch_to_tsquery('simple', %s)
                THEN ts_rank_cd(search_vector, websearch_to_tsquery('simple', %s))
                ELSE 0.0
            END AS rank_score
            """
        )
        select_params.extend([query.strip(), query.strip()])

    where_sql = " AND ".join(conditions)
    sql = f"""
        SELECT {MEMORY_SELECT_COLUMNS},
               {rank_sql}
        FROM memory_record
        WHERE {where_sql}
        ORDER BY rank_score DESC, importance DESC, confidence DESC, is_explicit DESC, updated_at DESC
        LIMIT %s
    """
    params = select_params + where_params + [limit]

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
        result_rows = [apply_memory_governance(dict(row)) for row in rows]
    def sort_key(item: Dict[str, Any]) -> Any:
        hybrid_score = float(item.get("hybrid_score", item.get("rank_score", 0.0)) or 0.0)
        explicit_bonus = 0.05 if item.get("is_explicit", False) else 0.0
        importance_bonus = min(int(item.get("importance", 0)), 10) * 0.01
        confidence_bonus = float(item.get("confidence", 0.0) or 0.0) * 0.02
        return (
            hybrid_score + explicit_bonus + importance_bonus + confidence_bonus,
            hybrid_score,
            float(item.get("rank_score", 0.0) or 0.0),
            float(item.get("vector_score", 0.0) or 0.0),
            item.get("updated_at"),
        )

    if not vector_scores:
        for row in result_rows:
            row["vector_score"] = 0.0
            row["hybrid_score"] = float(row.get("rank_score", 0.0) or 0.0)
        result_rows.sort(key=sort_key, reverse=True)
        return result_rows

    merged = []
    seen_ids = set()
    for row in result_rows:
        memory_id = int(row["id"])
        row["vector_score"] = vector_scores.get(memory_id, 0.0)
        row["hybrid_score"] = float(row["rank_score"]) + row["vector_score"]
        merged.append(row)
        seen_ids.add(memory_id)

    if vector_scores:
        with get_conn() as conn, conn.cursor() as cur:
            missing_ids = [memory_id for memory_id in vector_scores if memory_id not in seen_ids]
            if missing_ids:
                cur.execute(
                    """
                    SELECT
                           """
                    + MEMORY_SELECT_COLUMNS
                    + """,
                           0::float AS rank_score
                    FROM memory_record
                    WHERE id = ANY(%s)
                    ORDER BY updated_at DESC
                    """,
                    (missing_ids,),
                )
                for row in cur.fetchall():
                    payload = apply_memory_governance(dict(row))
                    payload["vector_score"] = vector_scores.get(int(payload["id"]), 0.0)
                    payload["hybrid_score"] = payload["vector_score"]
                    merged.append(payload)

    merged.sort(key=sort_key, reverse=True)
    return merged[:limit]


def search_memories_by_time_range(
    *,
    time_field: str,
    start_at: Optional[str] = None,
    end_at: Optional[str] = None,
    query: str = "",
    user_code: Optional[str] = None,
    memory_type: Optional[str] = None,
    tags: Optional[List[str]] = None,
    include_archived: bool = False,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    if time_field not in TIME_FIELD_SQL:
        raise ValueError(f"unsupported time field: {time_field}")

    resolved_user = _resolve_user(user_code)
    tags = tags or []
    field_sql = TIME_FIELD_SQL[time_field]
    conditions = ["user_code = %s", "deleted_at IS NULL", f"{field_sql} IS NOT NULL"]
    params: List[Any] = [resolved_user]

    if not include_archived:
        conditions.append(f"status = '{STATUS_ACTIVE}'")
    if start_at:
        conditions.append(f"{field_sql} >= %s")
        params.append(start_at)
    if end_at:
        conditions.append(f"{field_sql} <= %s")
        params.append(end_at)
    if memory_type:
        conditions.append("memory_type = %s")
        params.append(resolve_lookup_value(DOMAIN_MEMORY_TYPE, memory_type) or memory_type)
    if tags:
        conditions.append("tags ?| %s")
        params.append(tags)
    if query.strip():
        conditions.append(
            """
            (
                search_vector @@ websearch_to_tsquery('simple', %s)
                OR title ILIKE %s
                OR content ILIKE %s
                OR coalesce(summary, '') ILIKE %s
            )
            """
        )
        params.append(query.strip())
        like_query = "%" + query.strip() + "%"
        params.extend([like_query, like_query, like_query])

    where_sql = " AND ".join(conditions)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {MEMORY_SELECT_COLUMNS}
            FROM memory_record
            WHERE {where_sql}
            ORDER BY {field_sql} DESC, updated_at DESC, id DESC
            LIMIT %s
            """,
            params + [limit],
        )
        return [apply_memory_governance(dict(row)) for row in cur.fetchall()]


def upsert_memory(payload: Dict[str, Any]) -> Dict[str, Any]:
    resolved_user = _resolve_user(payload.get("user_code"))
    normalized_taxonomy = _normalize_memory_taxonomy(
        memory_type=payload.get("memory_type"),
        category=payload.get("category"),
        source_type=payload.get("source_type"),
        attribute_key=payload.get("attribute_key"),
        source_ref=payload.get("source_ref"),
    )
    payload = payload.copy()
    payload["memory_type"] = normalized_taxonomy["memory_type"]
    payload["source_type"] = normalized_taxonomy["source_type"]
    payload["category"] = payload.get("category") or normalized_taxonomy["category"]
    if normalized_taxonomy["attribute_key"]:
        payload["attribute_key"] = normalized_taxonomy["attribute_key"]
    existing = None
    if not payload.get("id"):
        existing = find_existing_memory(
            user_code=resolved_user,
            memory_type=payload["memory_type"],
            title=payload["title"],
            content=payload["content"],
        )
        if existing:
            payload = payload.copy()
            payload["id"] = int(existing["id"])
    tags = payload.get("tags") or []
    governed_payload = apply_memory_governance(
        {
            "memory_type": payload["memory_type"],
            "category": payload.get("category"),
            "title": payload["title"],
            "content": payload["content"],
            "summary": payload.get("summary"),
            "tags": tags,
            "confidence": payload.get("confidence", 0.7),
            "status": payload.get("status", STATUS_ACTIVE),
            "is_explicit": payload.get("is_explicit", False),
            "subject_key": payload.get("subject_key"),
            "related_subject_key": payload.get("related_subject_key"),
            "attribute_key": payload.get("attribute_key"),
            "value_text": payload.get("value_text"),
            "updated_at": existing.get("updated_at") if existing else None,
            "recall_count": existing.get("recall_count", 0) if existing else 0,
            "conflict_with_id": payload.get("conflict_with_id"),
            "valid_to": payload.get("valid_to"),
        }
    )
    values = {
        "user_code": resolved_user,
        "memory_type": payload["memory_type"],
        "category": payload.get("category"),
        "title": payload["title"],
        "content": payload["content"],
        "summary": payload.get("summary"),
        "tags": Json(tags),
        "source_type": payload.get("source_type", SOURCE_MANUAL),
        "source_ref": payload.get("source_ref"),
        "confidence": payload.get("confidence", 0.7),
        "importance": payload.get("importance", 5),
        "status": payload.get("status", STATUS_ACTIVE),
        "is_explicit": payload.get("is_explicit", False),
        "valid_from": payload.get("valid_from"),
        "valid_to": payload.get("valid_to"),
        "subject_key": payload.get("subject_key"),
        "related_subject_key": payload.get("related_subject_key"),
        "attribute_key": payload.get("attribute_key"),
        "value_text": payload.get("value_text"),
        "conflict_scope": payload.get("conflict_scope"),
        "sensitivity_level": governed_payload["sensitivity_level"],
        "disclosure_policy": governed_payload["disclosure_policy"],
        "lifecycle_state": governed_payload["lifecycle_state"],
        "stability_score": governed_payload["stability_score"],
    }
    with get_conn() as conn, conn.cursor() as cur:
        if payload.get("id"):
            cur.execute(
                """
                UPDATE memory_record
                SET memory_type = %(memory_type)s,
                    category = %(category)s,
                    title = %(title)s,
                    content = %(content)s,
                    summary = %(summary)s,
                    tags = %(tags)s,
                    source_type = %(source_type)s,
                    source_ref = %(source_ref)s,
                    confidence = %(confidence)s,
                    importance = %(importance)s,
                    status = %(status)s,
                    is_explicit = %(is_explicit)s,
                    valid_from = %(valid_from)s,
                    valid_to = %(valid_to)s,
                    subject_key = %(subject_key)s,
                    related_subject_key = %(related_subject_key)s,
                    attribute_key = %(attribute_key)s,
                    value_text = %(value_text)s,
                    conflict_scope = %(conflict_scope)s,
                    sensitivity_level = %(sensitivity_level)s,
                    disclosure_policy = %(disclosure_policy)s,
                    lifecycle_state = %(lifecycle_state)s,
                    stability_score = %(stability_score)s,
                    updated_at = now()
                WHERE id = %(id)s AND user_code = %(user_code)s AND deleted_at IS NULL
                RETURNING id
                """,
                values | {"id": payload["id"]},
            )
        else:
            cur.execute(
                """
                INSERT INTO memory_record (
                    user_code, memory_type, category, title, content, summary, tags,
                    source_type, source_ref, confidence, importance, status,
                    is_explicit, valid_from, valid_to,
                    subject_key, related_subject_key, attribute_key, value_text, conflict_scope,
                    sensitivity_level, disclosure_policy, lifecycle_state, stability_score
                ) VALUES (
                    %(user_code)s, %(memory_type)s, %(category)s, %(title)s, %(content)s, %(summary)s, %(tags)s,
                    %(source_type)s, %(source_ref)s, %(confidence)s, %(importance)s, %(status)s,
                    %(is_explicit)s, %(valid_from)s, %(valid_to)s,
                    %(subject_key)s, %(related_subject_key)s, %(attribute_key)s, %(value_text)s, %(conflict_scope)s,
                    %(sensitivity_level)s, %(disclosure_policy)s, %(lifecycle_state)s, %(stability_score)s
                )
                RETURNING id
                """,
                values,
            )
        row = cur.fetchone()
        conn.commit()
    result = get_memory(int(row["id"]), resolved_user) or {}
    try:
        embedding_source = (result.get("summary") or result.get("content") or result.get("title") or "").strip()
        if embedding_source:
            refresh_memory_embedding(int(row["id"]), resolved_user, embedding_source)
    except Exception:
        pass
    try:
        sync_entity_graph_for_memory(result)
    except Exception:
        pass
    return apply_memory_governance(result)


def mark_memories_recalled(memory_ids: List[int], user_code: Optional[str] = None) -> None:
    if not memory_ids:
        return
    resolved_user = _resolve_user(user_code)
    unique_ids = sorted({int(memory_id) for memory_id in memory_ids})
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE memory_record
            SET recall_count = recall_count + 1,
                last_recalled_at = now(),
                updated_at = now()
            WHERE user_code = %s
              AND id = ANY(%s)
              AND deleted_at IS NULL
            RETURNING id, confidence, is_explicit, memory_type, status,
                      valid_to, conflict_with_id, updated_at, recall_count, stability_score
            """,
            (resolved_user, unique_ids),
        )
        rows = [dict(row) for row in cur.fetchall()]
        for row in rows:
            lifecycle_state = derive_lifecycle_state(row)
            cur.execute(
                """
                UPDATE memory_record
                SET lifecycle_state = %s
                WHERE id = %s
                """,
                (lifecycle_state, row["id"]),
            )
        conn.commit()


def maintain_memory_store(
    *,
    user_code: Optional[str] = None,
    limit: int = 200,
    dry_run: bool = False,
    include_archived: bool = False,
    lifecycle_states: Optional[List[str]] = None,
    memory_types: Optional[List[str]] = None,
    categories: Optional[List[str]] = None,
) -> Dict[str, Any]:
    resolved_user = _resolve_user(user_code)
    conditions = ["user_code = %s", "deleted_at IS NULL"]
    params: List[Any] = [resolved_user]
    if not include_archived:
        conditions.append("status = %s")
        params.append(STATUS_ACTIVE)
    if lifecycle_states:
        conditions.append("lifecycle_state = ANY(%s)")
        params.append(lifecycle_states)
    if memory_types:
        conditions.append("memory_type = ANY(%s)")
        params.append(memory_types)
    if categories:
        conditions.append("category = ANY(%s)")
        params.append(categories)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {MEMORY_SELECT_COLUMNS}
            FROM memory_record
            WHERE {' AND '.join(conditions)}
            ORDER BY COALESCE(last_recalled_at, updated_at, created_at) ASC, id ASC
            LIMIT %s
            """,
            params + [limit],
        )
        rows = [dict(row) for row in cur.fetchall()]
        updates: List[Dict[str, Any]] = []
        lifecycle_counts: Dict[str, int] = {}
        for row in rows:
            governed = apply_memory_governance(row)
            lifecycle_state = str(governed.get("lifecycle_state") or "")
            lifecycle_counts[lifecycle_state] = lifecycle_counts.get(lifecycle_state, 0) + 1
            changed_fields: List[str] = []
            if round(float(row.get("stability_score") or 0.0), 4) != round(
                float(governed.get("stability_score") or 0.0), 4
            ):
                changed_fields.append("stability_score")
            for field in ("lifecycle_state", "sensitivity_level", "disclosure_policy"):
                if str(row.get(field) or "") != str(governed.get(field) or ""):
                    changed_fields.append(field)
            if not changed_fields:
                continue
            updates.append(
                {
                    "id": int(row["id"]),
                    "title": row.get("title"),
                    "lifecycle_state": lifecycle_state,
                    "sensitivity_level": governed.get("sensitivity_level"),
                    "disclosure_policy": governed.get("disclosure_policy"),
                    "stability_score": float(governed.get("stability_score") or 0.0),
                    "changed_fields": changed_fields,
                }
            )
            if not dry_run:
                cur.execute(
                    """
                    UPDATE memory_record
                    SET lifecycle_state = %s,
                        sensitivity_level = %s,
                        disclosure_policy = %s,
                        stability_score = %s,
                        updated_at = now()
                    WHERE id = %s AND user_code = %s
                    """,
                    (
                        governed.get("lifecycle_state"),
                        governed.get("sensitivity_level"),
                        governed.get("disclosure_policy"),
                        governed.get("stability_score"),
                        row["id"],
                        resolved_user,
                    ),
                )
        if not dry_run:
            conn.commit()
    return {
        "scanned_count": len(rows),
        "updated_count": len(updates),
        "dry_run": dry_run,
        "changed_ids": [item["id"] for item in updates],
        "lifecycle_counts": lifecycle_counts,
        "updated_memories": updates[:20],
        "filter_applied": {
            k: v for k, v in {
                "lifecycle_states": lifecycle_states,
                "memory_types": memory_types,
                "categories": categories,
            }.items() if v is not None
        },
    }


def promote_memory(payload: Dict[str, Any]) -> Dict[str, Any]:
    explicit = bool(payload.get("explicit"))
    title = payload.get("title") or payload["text"][:80]
    confidence = 0.95 if explicit else 0.6
    importance = 8 if explicit else 5
    return upsert_memory(
        {
            "user_code": payload.get("user_code"),
            "memory_type": payload.get("memory_type", "fact"),
            "title": title,
            "content": payload["text"],
            "summary": payload["text"][:240],
            "tags": payload.get("tags") or [],
            "source_type": payload.get("source_type", SOURCE_CONVERSATION),
            "source_ref": payload.get("source_ref"),
            "confidence": confidence,
            "importance": importance,
            "status": STATUS_ACTIVE,
            "is_explicit": explicit,
        }
    )


def archive_memory(memory_id: int, user_code: Optional[str] = None) -> Optional[Dict[str, Any]]:
    resolved_user = _resolve_user(user_code)
    existing = get_memory(memory_id, resolved_user)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE memory_record
            SET status = %s, updated_at = now()
            WHERE id = %s AND user_code = %s AND deleted_at IS NULL
            RETURNING id
            """,
            (STATUS_ARCHIVED, memory_id, resolved_user),
        )
        row = cur.fetchone()
        conn.commit()
    if not row:
        return None
    result = get_memory(int(row["id"]), resolved_user)
    try:
        refresh_entity_graph_for_subject(
            user_code=resolved_user,
            subject_key=(existing or result or {}).get("subject_key"),
        )
    except Exception:
        pass
    return result


def delete_memory(memory_id: int, user_code: Optional[str] = None) -> Optional[Dict[str, Any]]:
    resolved_user = _resolve_user(user_code)
    existing = get_memory(memory_id, resolved_user)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE memory_record
            SET status = %s, deleted_at = now(), updated_at = now()
            WHERE id = %s AND user_code = %s AND deleted_at IS NULL
            RETURNING id
            """,
            (STATUS_DELETED, memory_id, resolved_user),
        )
        row = cur.fetchone()
        conn.commit()
    if not row:
        return None
    result = get_memory(int(row["id"]), resolved_user)
    try:
        refresh_entity_graph_for_subject(
            user_code=resolved_user,
            subject_key=(existing or result or {}).get("subject_key"),
        )
    except Exception:
        pass
    return result




def find_duplicate_pairs(
    *,
    user_code: str,
    similarity_threshold: float = 0.92,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """查找语义相似度超过阈值的记忆对（两侧均过滤 user_code）。"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT a.memory_id AS master_candidate_id,
                   b.memory_id AS slave_candidate_id,
                   (a.embedding <=> b.embedding) AS distance
            FROM memory_vector_chunk a
            JOIN memory_vector_chunk b
                ON b.memory_id > a.memory_id
                AND b.chunk_index = 0
                AND b.user_code = %s
            WHERE a.chunk_index = 0
              AND a.user_code = %s
              AND (a.embedding <=> b.embedding) < (1.0 - %s)
            ORDER BY distance ASC
            LIMIT %s
            """,
            (user_code, user_code, similarity_threshold, limit * 2),
        )
        return [dict(row) for row in cur.fetchall()]


def merge_memory_pair(
    *,
    user_code: str,
    master_id: int,
    slave_id: int,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """合并 slave 到 master，slave 归档，master 追加内容和 tags。"""
    master = get_memory(master_id, user_code)
    slave = get_memory(slave_id, user_code)
    if not master or not slave:
        return {"error": "memory not found"}

    slave_content = str(slave.get("content") or "").strip()
    master_content = str(master.get("content") or "").strip()
    merged_content = master_content + "\n\n---\n" + slave_content
    if len(merged_content) > 4000:
        merged_content = merged_content[:4000] + "…（已截断）"

    master_tags = list(master.get("tags") or [])
    slave_tags = list(slave.get("tags") or [])
    merged_tags = list(dict.fromkeys(master_tags + slave_tags))

    if dry_run:
        return {
            "master_id": master_id,
            "slave_id": slave_id,
            "dry_run": True,
            "merged_content_preview": merged_content[:200],
        }

    with get_conn() as conn, conn.cursor() as cur:
        # slave 归档
        cur.execute(
            "UPDATE memory_record SET status = 'archived', updated_at = now() WHERE id = %s AND user_code = %s",
            (slave_id, user_code)
        )
        # master 设置 supersedes_id
        cur.execute(
            "UPDATE memory_record SET supersedes_id = %s, updated_at = now() WHERE id = %s AND user_code = %s",
            (slave_id, master_id, user_code)
        )
        # master 更新 content 和 tags
        cur.execute(
            "UPDATE memory_record SET content = %s, tags = %s::jsonb, updated_at = now() WHERE id = %s AND user_code = %s",
            (merged_content, json.dumps(merged_tags), master_id, user_code)
        )
        conn.commit()

    return {
        "master_id": master_id,
        "slave_id": slave_id,
        "dry_run": False,
    }


def merge_duplicate_memories(
    *,
    user_code: Optional[str] = None,
    similarity_threshold: float = 0.92,
    dry_run: bool = False,
    limit: int = 50,
) -> Dict[str, Any]:
    resolved_user = _resolve_user(user_code)
    pairs = find_duplicate_pairs(
        user_code=resolved_user,
        similarity_threshold=similarity_threshold,
        limit=limit,
    )
    valid_pairs = []
    for pair in pairs:
        master = get_memory(int(pair["master_candidate_id"]), resolved_user)
        slave = get_memory(int(pair["slave_candidate_id"]), resolved_user)
        if not master or not slave:
            continue
        if master.get("status") == "archived" or slave.get("status") == "archived":
            continue
        # 保留 confidence 更高者为 master；confidence 相同时取 updated_at 更新者
        slave_conf = float(slave.get("confidence") or 0)
        master_conf = float(master.get("confidence") or 0)
        if slave_conf > master_conf:
            master, slave = slave, master
        elif slave_conf == master_conf:
            if (slave.get("updated_at") or "") > (master.get("updated_at") or ""):
                master, slave = slave, master
        valid_pairs.append((master, slave))

    merged_pairs = []
    for master, slave in valid_pairs:
        result = merge_memory_pair(
            user_code=resolved_user,
            master_id=int(master["id"]),
            slave_id=int(slave["id"]),
            dry_run=dry_run,
        )
        merged_pairs.append(result)

    return {
        "merged_pairs": merged_pairs,
        "merged_count": len(merged_pairs),
        "dry_run": dry_run,
    }


def _search_memories_hybrid(
    *,
    user_code: str,
    query_text: str,
    query_vec: List[float],
    limit: int,
    memory_type: Optional[str] = None,
    tags: Optional[List[str]] = None,
    include_archived: bool = False,
) -> List[Dict[str, Any]]:
    archived_filter = "" if include_archived else "AND mr.status != 'archived'"
    extra_conditions = ""
    extra_params: List[Any] = []
    if memory_type:
        extra_conditions += " AND mr.memory_type = %s"
        extra_params.append(resolve_lookup_value(DOMAIN_MEMORY_TYPE, memory_type) or memory_type)
    if tags:
        extra_conditions += " AND mr.tags ?| %s"
        extra_params.append(tags)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT mr.*,
                   ts_rank_cd(mr.search_vector, websearch_to_tsquery('simple', %s)) AS rank_score,
                   (mvc.embedding <=> %s::vector) AS vector_distance,
                   COALESCE(
                       ts_rank_cd(mr.search_vector, websearch_to_tsquery('simple', %s)) * 0.4
                       + (1.0 - (mvc.embedding <=> %s::vector)) * 0.6,
                       ts_rank_cd(mr.search_vector, websearch_to_tsquery('simple', %s)) * 0.4
                   ) AS hybrid_score
            FROM memory_record mr
            LEFT JOIN memory_vector_chunk mvc ON mvc.memory_id = mr.id AND mvc.chunk_index = 0
            WHERE mr.user_code = %s
              AND mr.deleted_at IS NULL
              {archived_filter}
              {extra_conditions}
              AND (
                  mr.search_vector @@ websearch_to_tsquery('simple', %s)
                  OR (mvc.embedding IS NOT NULL AND (mvc.embedding <=> %s::vector) < 0.5)
              )
            ORDER BY hybrid_score DESC NULLS LAST
            LIMIT %s
            """,
            (
                query_text,          # rank_score
                Vector(query_vec),   # vector_distance
                query_text,          # COALESCE rank
                Vector(query_vec),   # COALESCE vector
                query_text,          # COALESCE else rank
                user_code,           # WHERE user_code
                *extra_params,       # WHERE memory_type / tags (optional)
                query_text,          # WHERE full-text
                Vector(query_vec),   # WHERE vector
                limit,
            ),
        )
        return [apply_memory_governance(dict(row)) for row in cur.fetchall()]
