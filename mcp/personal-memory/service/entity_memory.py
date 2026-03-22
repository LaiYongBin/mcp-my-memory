"""Derived entity and relationship summaries from stored memories."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

from service.db import get_conn, get_settings


_SENSITIVITY_ORDER = {
    "public": 0,
    "normal": 1,
    "sensitive": 2,
    "restricted": 3,
}

_DISCLOSURE_ORDER = {
    "normal": 0,
    "gentle": 1,
    "user_confirm": 2,
    "internal_only": 3,
}


def _resolve_user(user_code: Optional[str]) -> str:
    return user_code or str(get_settings()["memory_user"])


def _display_name(subject_key: str) -> str:
    cleaned = str(subject_key or "").strip()
    if not cleaned:
        return ""
    for prefix in ("friend_", "partner_", "family_", "project_", "team_", "user_"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
            break
    return cleaned.replace("_", " ").strip()


def _relation_type(subject_key: str) -> str:
    cleaned = str(subject_key or "").strip().lower()
    for prefix in ("friend", "partner", "family", "project", "team", "user"):
        if cleaned.startswith(prefix + "_") or cleaned == prefix:
            return prefix
    return "entity"


def summarize_entities_from_memories(memories: List[Dict[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in memories:
        subject_key = str(item.get("subject_key") or "").strip()
        if not subject_key:
            continue
        grouped[subject_key].append(item)

    entities: List[Dict[str, Any]] = []
    for subject_key, rows in grouped.items():
        sensitivity = max(
            (str(row.get("sensitivity_level") or "normal") for row in rows),
            key=lambda value: _SENSITIVITY_ORDER.get(value, 1),
        )
        disclosure = max(
            (str(row.get("disclosure_policy") or "normal") for row in rows),
            key=lambda value: _DISCLOSURE_ORDER.get(value, 0),
        )
        attributes = sorted(
            {
                str(row.get("attribute_key") or "").strip()
                for row in rows
                if str(row.get("attribute_key") or "").strip()
            }
        )
        categories = sorted(
            {
                str(row.get("category") or "").strip()
                for row in rows
                if str(row.get("category") or "").strip()
            }
        )
        latest_title = max(
            rows,
            key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""),
        ).get("title")
        entities.append(
            {
                "subject_key": subject_key,
                "display_name": _display_name(subject_key),
                "relation_type": _relation_type(subject_key),
                "memory_count": len(rows),
                "categories": categories,
                "attribute_keys": attributes,
                "latest_title": latest_title,
                "sensitivity_level": sensitivity,
                "disclosure_policy": disclosure,
            }
        )

    entities.sort(
        key=lambda item: (
            -int(item.get("memory_count") or 0),
            item.get("subject_key") or "",
        )
    )
    return entities[:limit]


def search_entities(
    *,
    query: str = "",
    user_code: Optional[str] = None,
    subject_key: Optional[str] = None,
    include_archived: bool = False,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    resolved_user = _resolve_user(user_code)
    conditions = ["user_code = %s", "deleted_at IS NULL", "subject_key IS NOT NULL", "subject_key <> ''"]
    params: List[Any] = [resolved_user]
    if not include_archived:
        conditions.append("status = 'active'")
    if subject_key:
        conditions.append("subject_key = %s")
        params.append(subject_key)
    if query:
        conditions.append(
            """
            (
                subject_key ILIKE %s OR
                title ILIKE %s OR
                content ILIKE %s OR
                COALESCE(value_text, '') ILIKE %s
            )
            """
        )
        like = f"%{query}%"
        params.extend([like, like, like, like])
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT subject_key, title, content, category, attribute_key, value_text,
                   sensitivity_level, disclosure_policy, created_at, updated_at
            FROM memory_record
            WHERE {' AND '.join(conditions)}
            ORDER BY updated_at DESC, id DESC
            LIMIT %s
            """,
            params + [max(limit * 8, limit)],
        )
        rows = [dict(row) for row in cur.fetchall()]
    return summarize_entities_from_memories(rows, limit=limit)
