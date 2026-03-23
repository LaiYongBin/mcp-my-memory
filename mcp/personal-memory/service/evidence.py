"""Evidence accumulation for inferred and observed memories."""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Sequence

from psycopg.types.json import Json

from service.constants import (
    ACTION_LONG_TERM,
    EVIDENCE_EXPLICIT,
    EVIDENCE_INFERRED,
    EVIDENCE_OBSERVED,
    STATUS_ACTIVE,
    TIME_EPHEMERAL,
    TIME_LONG_TERM,
    TIME_MID_TERM,
    TIME_SHORT_TERM,
)
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
        EVIDENCE_EXPLICIT: 1.2,
        EVIDENCE_OBSERVED: 0.9,
        EVIDENCE_INFERRED: 0.75,
    }.get(str(item.get("evidence_type") or EVIDENCE_OBSERVED), 0.85)
    scope_bonus = {
        TIME_LONG_TERM: 0.25,
        TIME_MID_TERM: 0.12,
        TIME_SHORT_TERM: 0.05,
        TIME_EPHEMERAL: 0.0,
    }.get(str(item.get("time_scope") or TIME_MID_TERM), 0.0)
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
            FROM memory_signal
            WHERE user_code = %s
              AND conflict_scope = %s
              AND status = %s
            ORDER BY support_score DESC, occurrence_count DESC, last_seen_at DESC
            """,
            (user_code, conflict_scope, STATUS_ACTIVE),
        )
        return [dict(row) for row in cur.fetchall()]


def _update_existing_evidence(*, evidence_id: int, item: Dict[str, Any], delta: float) -> Optional[Dict[str, Any]]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE memory_signal
            SET category = %s,
                latest_claim = %s,
                evidence_type = CASE
                    WHEN %s = %s OR evidence_type = %s THEN %s
                    WHEN %s = %s OR evidence_type = %s THEN %s
                    ELSE %s
                END,
                time_scope = CASE
                    WHEN %s = %s OR time_scope = %s THEN %s
                    WHEN %s = %s OR time_scope = %s THEN %s
                    WHEN %s = %s OR time_scope = %s THEN %s
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
                str(item.get("evidence_type") or EVIDENCE_OBSERVED),
                EVIDENCE_EXPLICIT,
                EVIDENCE_EXPLICIT,
                EVIDENCE_EXPLICIT,
                str(item.get("evidence_type") or EVIDENCE_OBSERVED),
                EVIDENCE_OBSERVED,
                EVIDENCE_OBSERVED,
                EVIDENCE_OBSERVED,
                str(item.get("time_scope") or TIME_MID_TERM),
                TIME_LONG_TERM,
                TIME_LONG_TERM,
                TIME_LONG_TERM,
                str(item.get("time_scope") or TIME_MID_TERM),
                TIME_MID_TERM,
                TIME_MID_TERM,
                TIME_MID_TERM,
                str(item.get("time_scope") or TIME_MID_TERM),
                TIME_SHORT_TERM,
                TIME_SHORT_TERM,
                TIME_SHORT_TERM,
                str(item.get("time_scope") or TIME_MID_TERM),
                delta,
                Json(list(item.get("tags") or [])),
                evidence_id,
            ),
        )
        row = cur.fetchone()
        conn.commit()
        return dict(row) if row else None


def _insert_new_evidence(*, resolved_user: str, slot: dict, item: dict, delta: float):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO memory_signal (
                user_code, category, subject_key, attribute_key, value_text, latest_claim,
                conflict_scope, evidence_type, time_scope, support_score, occurrence_count,
                promoted_memory_id, status, tags, first_seen_at, last_seen_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                NULL, %s, %s, now(), now()
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
                str(item.get("evidence_type") or EVIDENCE_OBSERVED),
                str(item.get("time_scope") or TIME_MID_TERM),
                delta,
                1,
                STATUS_ACTIVE,
                Json(list(item.get("tags") or [])),
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
    return _insert_new_evidence(resolved_user=resolved_user, slot=slot, item=item, delta=delta)


def evidence_supports_promotion(item: Dict[str, Any], evidence: Optional[Dict[str, Any]]) -> bool:
    if not evidence or str(item.get("action") or "") != ACTION_LONG_TERM:
        return False
    evidence_type = str(evidence.get("evidence_type") or item.get("evidence_type") or EVIDENCE_OBSERVED)
    occurrence_count = int(evidence.get("occurrence_count") or 0)
    support_score = float(evidence.get("support_score") or 0.0)
    confidence = float(item.get("confidence") or 0.0)
    time_scope = str(item.get("time_scope") or evidence.get("time_scope") or TIME_MID_TERM)

    if evidence_type == EVIDENCE_EXPLICIT and time_scope == TIME_LONG_TERM and confidence >= 0.85:
        return True
    if evidence_type == EVIDENCE_EXPLICIT:
        return occurrence_count >= 2 or support_score >= 1.5
    if evidence_type == EVIDENCE_OBSERVED:
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
            UPDATE memory_signal
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


def accumulate_evidence_batch(
    *,
    user_code: Optional[str],
    items: List[Dict[str, Any]],
) -> List[Optional[Dict[str, Any]]]:
    """批量积累证据：先批量 SELECT 所有 conflict_scope，再逐条 UPDATE/INSERT。"""
    if not items:
        return []
    resolved_user = _resolve_user(user_code)
    # 1. 收集需要查询的 conflict_scopes
    results: List[Optional[Dict[str, Any]]] = [None] * len(items)
    slots_by_scope: Dict[str, List] = {}
    for idx, item in enumerate(items):
        slot = _normalized_slot(item)
        if not slot:
            continue
        scope = slot["conflict_scope"]
        delta = _support_delta(item)
        slots_by_scope.setdefault(scope, []).append((idx, slot, item, delta))

    if not slots_by_scope:
        return results

    # 2. 批量 SELECT 所有 scopes（一次查询）
    scopes = list(slots_by_scope.keys())
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, user_code, category, subject_key, attribute_key, value_text, latest_claim,
                   conflict_scope, evidence_type, time_scope, support_score, occurrence_count,
                   promoted_memory_id, status, tags, first_seen_at, last_seen_at, created_at, updated_at
            FROM memory_signal
            WHERE user_code = %s
              AND conflict_scope = ANY(%s)
              AND status = %s
            ORDER BY support_score DESC, occurrence_count DESC, last_seen_at DESC
            """,
            (resolved_user, scopes, STATUS_ACTIVE),
        )
        all_rows = [dict(r) for r in cur.fetchall()]

    # 3. 按 scope 分组
    rows_by_scope: Dict[str, List[Dict[str, Any]]] = {}
    for row in all_rows:
        rows_by_scope.setdefault(str(row["conflict_scope"]), []).append(row)

    # 4. 逐 scope 处理（UPDATE/INSERT）
    for scope, entries in slots_by_scope.items():
        existing_rows = rows_by_scope.get(scope, [])
        for idx, slot, item, delta in entries:
            target = _find_merge_target(existing_rows, value_text=slot["value_text"], tags=item.get("tags") or [])
            if target:
                result = _update_existing_evidence(evidence_id=int(target["id"]), item=item, delta=delta)
            else:
                result = _insert_new_evidence(resolved_user=resolved_user, slot=slot, item=item, delta=delta)
            results[idx] = result
    return results


def list_evidence(*, user_code: Optional[str] = None, conflict_scope: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    resolved_user = _resolve_user(user_code)
    conditions = ["user_code = %s", "status = %s"]
    params: List[Any] = [resolved_user, STATUS_ACTIVE]
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
            FROM memory_signal
            WHERE {where_sql}
            ORDER BY support_score DESC, occurrence_count DESC, last_seen_at DESC
            LIMIT %s
            """,
            params + [limit],
        )
        return [dict(row) for row in cur.fetchall()]
