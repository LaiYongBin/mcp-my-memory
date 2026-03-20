"""Evidence accumulation for inferred and observed memories."""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Sequence

from psycopg.types.json import Json

from service.db import get_conn, get_settings


def _resolve_user(user_code: Optional[str]) -> str:
    return user_code or str(get_settings()["memory_user"])


def _normalized_slot(item: Dict[str, Any]) -> Optional[Dict[str, str]]:
    subject = str(item.get("subject") or "").strip()
    attribute = str(item.get("attribute") or "").strip()
    value = str(item.get("value") or item.get("claim") or "").strip()
    if not subject or not attribute or not value:
        return None
    return {
        "subject_key": subject,
        "attribute_key": attribute,
        "value_text": value,
        "conflict_scope": str(item.get("conflict_scope") or f"{subject}.{attribute}"),
    }


def _support_delta(item: Dict[str, Any]) -> float:
    confidence = max(0.2, float(item.get("confidence") or 0.0))
    evidence_weight = {
        "explicit": 1.2,
        "observed": 0.9,
        "inferred": 0.75,
    }.get(str(item.get("evidence_type") or "observed"), 0.85)
    scope_bonus = {
        "long_term": 0.25,
        "mid_term": 0.12,
        "short_term": 0.05,
        "ephemeral": 0.0,
    }.get(str(item.get("time_scope") or "mid_term"), 0.0)
    return round(confidence * evidence_weight + scope_bonus, 4)


def _tag_set(tags: Sequence[Any]) -> set[str]:
    return {str(tag).strip().lower() for tag in tags if str(tag).strip()}


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, left.lower(), right.lower()).ratio()


def _find_merge_target(
    existing_rows: List[Dict[str, Any]],
    *,
    value_text: str,
    tags: Sequence[Any],
) -> Optional[Dict[str, Any]]:
    wanted_tags = _tag_set(tags)
    best_row = None
    best_score = 0.0
    for row in existing_rows:
        row_value = str(row.get("value_text") or "").strip()
        if not row_value:
            continue
        if row_value == value_text:
            return row
        overlap = len(wanted_tags & _tag_set(row.get("tags") or []))
        similarity = _similarity(value_text, row_value)
        score = overlap + similarity
        if overlap >= 1 or similarity >= 0.72:
            if score > best_score:
                best_score = score
                best_row = row
    return best_row


def _fetch_existing_rows(*, user_code: str, conflict_scope: str) -> List[Dict[str, Any]]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, user_code, category, subject_key, attribute_key, value_text, latest_claim,
                   conflict_scope, evidence_type, time_scope, support_score, occurrence_count,
                   promoted_memory_id, status, tags, first_seen_at, last_seen_at, created_at, updated_at
            FROM memory_evidence
            WHERE user_code = %s
              AND conflict_scope = %s
              AND status = 'active'
            ORDER BY support_score DESC, occurrence_count DESC, last_seen_at DESC
            """,
            (user_code, conflict_scope),
        )
        return [dict(row) for row in cur.fetchall()]


def _update_existing_evidence(*, evidence_id: int, item: Dict[str, Any], delta: float) -> Optional[Dict[str, Any]]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE memory_evidence
            SET category = %s,
                latest_claim = %s,
                evidence_type = CASE
                    WHEN %s = 'explicit' OR evidence_type = 'explicit' THEN 'explicit'
                    WHEN %s = 'observed' OR evidence_type = 'observed' THEN 'observed'
                    ELSE 'inferred'
                END,
                time_scope = CASE
                    WHEN %s = 'long_term' OR time_scope = 'long_term' THEN 'long_term'
                    WHEN %s = 'mid_term' OR time_scope = 'mid_term' THEN 'mid_term'
                    WHEN %s = 'short_term' OR time_scope = 'short_term' THEN 'short_term'
                    ELSE %s
                END,
                support_score = support_score + %s,
                occurrence_count = occurrence_count + 1,
                tags = (
                    SELECT jsonb_agg(DISTINCT value)
                    FROM jsonb_array_elements(COALESCE(tags, '[]'::jsonb) || (%s)::jsonb)
                ),
                last_seen_at = now(),
                updated_at = now()
            WHERE id = %s
            RETURNING id, user_code, category, subject_key, attribute_key, value_text, latest_claim,
                      conflict_scope, evidence_type, time_scope, support_score, occurrence_count,
                      promoted_memory_id, status, tags, first_seen_at, last_seen_at, created_at, updated_at
            """,
            (
                str(item.get("category") or "generic_memory"),
                str(item.get("claim") or item.get("value") or ""),
                str(item.get("evidence_type") or "observed"),
                str(item.get("evidence_type") or "observed"),
                str(item.get("time_scope") or "mid_term"),
                str(item.get("time_scope") or "mid_term"),
                str(item.get("time_scope") or "mid_term"),
                str(item.get("time_scope") or "mid_term"),
                delta,
                Json(list(item.get("tags") or [])),
                evidence_id,
            ),
        )
        row = cur.fetchone()
        conn.commit()
        return dict(row) if row else None


def accumulate_evidence(*, user_code: Optional[str], item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    slot = _normalized_slot(item)
    if not slot:
        return None
    resolved_user = _resolve_user(user_code)
    delta = _support_delta(item)
    existing_rows = _fetch_existing_rows(user_code=resolved_user, conflict_scope=slot["conflict_scope"])
    target = _find_merge_target(existing_rows, value_text=slot["value_text"], tags=item.get("tags") or [])
    if target:
        return _update_existing_evidence(evidence_id=int(target["id"]), item=item, delta=delta)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO memory_evidence (
                user_code, category, subject_key, attribute_key, value_text, latest_claim,
                conflict_scope, evidence_type, time_scope, support_score, occurrence_count,
                promoted_memory_id, status, tags, first_seen_at, last_seen_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                NULL, 'active', %s, now(), now()
            )
            RETURNING id, user_code, category, subject_key, attribute_key, value_text, latest_claim,
                      conflict_scope, evidence_type, time_scope, support_score, occurrence_count,
                      promoted_memory_id, status, tags, first_seen_at, last_seen_at, created_at, updated_at
            """,
            (
                resolved_user,
                str(item.get("category") or "generic_memory"),
                slot["subject_key"],
                slot["attribute_key"],
                slot["value_text"],
                str(item.get("claim") or slot["value_text"]),
                slot["conflict_scope"],
                str(item.get("evidence_type") or "observed"),
                str(item.get("time_scope") or "mid_term"),
                delta,
                1,
                Json(list(item.get("tags") or [])),
            ),
        )
        row = cur.fetchone()
        conn.commit()
        return dict(row) if row else None


def evidence_supports_promotion(item: Dict[str, Any], evidence: Optional[Dict[str, Any]]) -> bool:
    if not evidence or str(item.get("action") or "") != "long_term":
        return False
    evidence_type = str(evidence.get("evidence_type") or item.get("evidence_type") or "observed")
    occurrence_count = int(evidence.get("occurrence_count") or 0)
    support_score = float(evidence.get("support_score") or 0.0)
    confidence = float(item.get("confidence") or 0.0)
    time_scope = str(item.get("time_scope") or evidence.get("time_scope") or "mid_term")

    if evidence_type == "explicit" and time_scope == "long_term" and confidence >= 0.8:
        return True
    if evidence_type == "explicit":
        return occurrence_count >= 2 or support_score >= 1.5
    if evidence_type == "observed":
        return occurrence_count >= 2 and support_score >= 1.6
    return occurrence_count >= 3 and support_score >= 2.0


def promoted_confidence(item: Dict[str, Any], evidence: Optional[Dict[str, Any]]) -> float:
    base_confidence = float(item.get("confidence") or 0.5)
    if not evidence:
        return min(0.95, base_confidence)
    occurrence_count = int(evidence.get("occurrence_count") or 1)
    support_score = float(evidence.get("support_score") or 0.0)
    boosted = max(base_confidence, 0.5 + (occurrence_count - 1) * 0.1 + support_score * 0.08)
    return round(min(0.95, boosted), 4)


def mark_evidence_promoted(evidence_id: int, memory_id: int) -> Optional[Dict[str, Any]]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE memory_evidence
            SET promoted_memory_id = %s, updated_at = now()
            WHERE id = %s
            RETURNING id, user_code, category, subject_key, attribute_key, value_text, latest_claim,
                      conflict_scope, evidence_type, time_scope, support_score, occurrence_count,
                      promoted_memory_id, status, tags, first_seen_at, last_seen_at, created_at, updated_at
            """,
            (memory_id, evidence_id),
        )
        row = cur.fetchone()
        conn.commit()
        return dict(row) if row else None


def list_evidence(*, user_code: Optional[str] = None, conflict_scope: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    resolved_user = _resolve_user(user_code)
    conditions = ["user_code = %s", "status = 'active'"]
    params: List[Any] = [resolved_user]
    if conflict_scope:
        conditions.append("conflict_scope = %s")
        params.append(conflict_scope)
    where_sql = " AND ".join(conditions)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id, user_code, category, subject_key, attribute_key, value_text, latest_claim,
                   conflict_scope, evidence_type, time_scope, support_score, occurrence_count,
                   promoted_memory_id, status, tags, first_seen_at, last_seen_at, created_at, updated_at
            FROM memory_evidence
            WHERE {where_sql}
            ORDER BY support_score DESC, occurrence_count DESC, last_seen_at DESC
            LIMIT %s
            """,
            params + [limit],
        )
        return [dict(row) for row in cur.fetchall()]
