"""Governed registries for expandable taxonomy domains."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Dict, List, Optional

from psycopg.types.json import Json

from service.constants import (
    STATUS_ACTIVE,
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REJECTED,
)
from service.db import get_conn, get_settings


DOMAIN_MEMORY_TYPE = "memory_type"
DOMAIN_SOURCE_TYPE = "source_type"
DOMAIN_CATEGORY = "category"
DOMAIN_ATTRIBUTE_KEY = "attribute_key"

DOMAIN_GOVERNANCE_FIXED = "fixed"
DOMAIN_GOVERNANCE_MANUAL_REVIEW = "manual_review"
DOMAIN_GOVERNANCE_AUTO_APPROVE = "auto_approve"


def _resolve_actor(created_by: Optional[str] = None) -> str:
    return created_by or str(get_settings()["memory_user"])


def normalize_domain_key(value: str) -> str:
    cleaned = re.sub(r"[\s/]+", "_", str(value or "").strip().lower())
    cleaned = re.sub(r"[^a-z0-9_-]+", "", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_-")
    return cleaned


@lru_cache(maxsize=64)
def get_domain_definition(domain_name: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT domain_name, domain_kind, governance_mode, default_value_key,
                   description, is_system, created_at, updated_at
            FROM domain_registry
            WHERE domain_name = %s
            """,
            (domain_name,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


@lru_cache(maxsize=512)
def lookup_domain_value(
    domain_name: str, value_key: str, include_archived: bool = False
) -> Optional[Dict[str, Any]]:
    conditions = ["domain_name = %s", "value_key = %s"]
    params: List[Any] = [domain_name, value_key]
    if not include_archived:
        conditions.append("status = %s")
        params.append(STATUS_ACTIVE)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id, domain_name, value_key, display_name, description, status,
                   is_builtin, created_by, metadata, created_at, updated_at
            FROM domain_value
            WHERE {' AND '.join(conditions)}
            """,
            params,
        )
        row = cur.fetchone()
        return dict(row) if row else None


@lru_cache(maxsize=512)
def lookup_domain_alias(domain_name: str, alias_key: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, domain_name, alias_key, canonical_value_key, created_at
            FROM domain_value_alias
            WHERE domain_name = %s AND alias_key = %s
            """,
            (domain_name, alias_key),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def list_domain_values(domain_name: str, include_archived: bool = False) -> List[Dict[str, Any]]:
    conditions = ["domain_name = %s"]
    params: List[Any] = [domain_name]
    if not include_archived:
        conditions.append("status = %s")
        params.append(STATUS_ACTIVE)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id, domain_name, value_key, display_name, description, status,
                   is_builtin, created_by, metadata, created_at, updated_at
            FROM domain_value
            WHERE {' AND '.join(conditions)}
            ORDER BY is_builtin DESC, value_key ASC
            """,
            params,
        )
        return [dict(row) for row in cur.fetchall()]


def list_domain_candidates(
    domain_name: Optional[str] = None,
    *,
    status: Optional[str] = STATUS_PENDING,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    conditions: List[str] = []
    params: List[Any] = []
    if domain_name:
        conditions.append("domain_name = %s")
        params.append(domain_name)
    if status:
        conditions.append("status = %s")
        params.append(status)
    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id, domain_name, proposed_value_key, normalized_value_key, canonical_value_key,
                   source, source_ref, reason, confidence, status, created_by, metadata,
                   created_at, updated_at
            FROM domain_value_candidate
            {where_sql}
            ORDER BY updated_at DESC, id DESC
            LIMIT %s
            """,
            params + [limit],
        )
        return [dict(row) for row in cur.fetchall()]


def create_domain_candidate(
    *,
    domain_name: str,
    proposed_value_key: str,
    normalized_value_key: str,
    source: str,
    source_ref: Optional[str] = None,
    reason: Optional[str] = None,
    confidence: float = 0.6,
    created_by: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    actor = _resolve_actor(created_by)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, domain_name, proposed_value_key, normalized_value_key, canonical_value_key,
                   source, source_ref, reason, confidence, status, created_by, metadata,
                   created_at, updated_at
            FROM domain_value_candidate
            WHERE domain_name = %s
              AND normalized_value_key = %s
              AND status = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (domain_name, normalized_value_key, STATUS_PENDING),
        )
        existing = cur.fetchone()
        if existing:
            return dict(existing)
        cur.execute(
            """
            INSERT INTO domain_value_candidate (
                domain_name, proposed_value_key, normalized_value_key, canonical_value_key,
                source, source_ref, reason, confidence, status, created_by, metadata
            ) VALUES (%s, %s, %s, NULL, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, domain_name, proposed_value_key, normalized_value_key, canonical_value_key,
                      source, source_ref, reason, confidence, status, created_by, metadata,
                      created_at, updated_at
            """,
            (
                domain_name,
                proposed_value_key,
                normalized_value_key,
                source,
                source_ref,
                reason,
                confidence,
                STATUS_PENDING,
                actor,
                Json(metadata or {}),
            ),
        )
        row = cur.fetchone()
        conn.commit()
        return dict(row)


def _create_domain_value(
    *,
    domain_name: str,
    value_key: str,
    display_name: Optional[str],
    description: Optional[str],
    created_by: Optional[str],
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    actor = _resolve_actor(created_by)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO domain_value (
                domain_name, value_key, display_name, description, status,
                is_builtin, created_by, metadata
            ) VALUES (%s, %s, %s, %s, %s, FALSE, %s, %s)
            ON CONFLICT (domain_name, value_key)
            DO UPDATE SET
                display_name = COALESCE(EXCLUDED.display_name, domain_value.display_name),
                description = COALESCE(EXCLUDED.description, domain_value.description),
                metadata = COALESCE(domain_value.metadata, '{}'::jsonb) || COALESCE(EXCLUDED.metadata, '{}'::jsonb),
                updated_at = now()
            RETURNING id, domain_name, value_key, display_name, description, status,
                      is_builtin, created_by, metadata, created_at, updated_at
            """,
            (
                domain_name,
                value_key,
                display_name or value_key,
                description,
                STATUS_ACTIVE,
                actor,
                Json(metadata or {}),
            ),
        )
        row = cur.fetchone()
        conn.commit()
    lookup_domain_value.cache_clear()
    return dict(row)


def _upsert_domain_alias(
    *,
    domain_name: str,
    alias_key: str,
    canonical_value_key: str,
) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO domain_value_alias (
                domain_name, alias_key, canonical_value_key
            ) VALUES (%s, %s, %s)
            ON CONFLICT (domain_name, alias_key)
            DO UPDATE SET canonical_value_key = EXCLUDED.canonical_value_key
            RETURNING id, domain_name, alias_key, canonical_value_key, created_at
            """,
            (domain_name, alias_key, canonical_value_key),
        )
        row = cur.fetchone()
        conn.commit()
    lookup_domain_alias.cache_clear()
    return dict(row)


def approve_domain_candidate(
    candidate_id: int,
    *,
    canonical_value_key: Optional[str] = None,
    create_alias: bool = True,
    created_by: Optional[str] = None,
) -> Dict[str, Any]:
    actor = _resolve_actor(created_by)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, domain_name, proposed_value_key, normalized_value_key, canonical_value_key,
                   source, source_ref, reason, confidence, status, created_by, metadata,
                   created_at, updated_at
            FROM domain_value_candidate
            WHERE id = %s
            """,
            (candidate_id,),
        )
        candidate_row = cur.fetchone()
        if not candidate_row:
            raise ValueError("domain candidate not found")
        candidate = dict(candidate_row)
        if candidate["status"] != STATUS_PENDING:
            value = lookup_domain_value(
                candidate["domain_name"],
                candidate["canonical_value_key"] or candidate["normalized_value_key"],
                include_archived=True,
            )
            return {"candidate": candidate, "value": value, "alias": None}

    target_value_key = normalize_domain_key(
        str(canonical_value_key or candidate["canonical_value_key"] or candidate["normalized_value_key"])
    )
    if not target_value_key:
        raise ValueError("canonical value key is required")
    value = lookup_domain_value(
        str(candidate["domain_name"]),
        target_value_key,
        include_archived=True,
    )
    if not value:
        value = _create_domain_value(
            domain_name=str(candidate["domain_name"]),
            value_key=target_value_key,
            display_name=str(
                candidate["proposed_value_key"]
                if target_value_key == str(candidate["normalized_value_key"])
                else target_value_key
            ),
            description=str(candidate["reason"] or ""),
            created_by=actor,
            metadata={"source": candidate.get("source"), "source_ref": candidate.get("source_ref")},
        )
    alias = None
    normalized_candidate = str(candidate["normalized_value_key"])
    if create_alias and normalized_candidate and normalized_candidate != str(value["value_key"]):
        alias = _upsert_domain_alias(
            domain_name=str(candidate["domain_name"]),
            alias_key=normalized_candidate,
            canonical_value_key=str(value["value_key"]),
        )
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE domain_value_candidate
            SET canonical_value_key = %s,
                status = %s,
                updated_at = now()
            WHERE id = %s
            RETURNING id, domain_name, proposed_value_key, normalized_value_key, canonical_value_key,
                      source, source_ref, reason, confidence, status, created_by, metadata,
                      created_at, updated_at
            """,
            (str(value["value_key"]), STATUS_APPROVED, candidate_id),
        )
        candidate_row = cur.fetchone()
        conn.commit()
    return {"candidate": dict(candidate_row), "value": value, "alias": alias}


def reject_domain_candidate(
    candidate_id: int,
    *,
    reason: Optional[str] = None,
    created_by: Optional[str] = None,
) -> Dict[str, Any]:
    actor = _resolve_actor(created_by)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE domain_value_candidate
            SET status = %s,
                metadata = COALESCE(metadata, '{}'::jsonb) || %s,
                updated_at = now()
            WHERE id = %s
            RETURNING id, domain_name, proposed_value_key, normalized_value_key, canonical_value_key,
                      source, source_ref, reason, confidence, status, created_by, metadata,
                      created_at, updated_at
            """,
            (
                STATUS_REJECTED,
                Json(
                    {
                        "review_reason": reason or "",
                        "reviewed_by": actor,
                    }
                ),
                candidate_id,
            ),
        )
        row = cur.fetchone()
        conn.commit()
    if not row:
        raise ValueError("domain candidate not found")
    candidate = dict(row)
    value = None
    if candidate.get("canonical_value_key"):
        value = lookup_domain_value(
            str(candidate["domain_name"]),
            str(candidate["canonical_value_key"]),
            include_archived=True,
        )
    return {"candidate": candidate, "value": value}


def merge_domain_alias(
    *,
    domain_name: str,
    alias_key: str,
    canonical_value_key: str,
    candidate_id: Optional[int] = None,
    created_by: Optional[str] = None,
) -> Dict[str, Any]:
    normalized_alias = normalize_domain_key(alias_key)
    normalized_canonical = normalize_domain_key(canonical_value_key)
    if not normalized_alias or not normalized_canonical:
        raise ValueError("alias_key and canonical_value_key are required")
    value = lookup_domain_value(domain_name, normalized_canonical, include_archived=True)
    if not value:
        raise ValueError("canonical domain value not found")
    alias = None
    candidate = None
    if normalized_alias != normalized_canonical:
        alias = _upsert_domain_alias(
            domain_name=domain_name,
            alias_key=normalized_alias,
            canonical_value_key=normalized_canonical,
        )
    if candidate_id is not None:
        approved = approve_domain_candidate(
            candidate_id,
            canonical_value_key=normalized_canonical,
            create_alias=normalized_alias != normalized_canonical,
            created_by=created_by,
        )
        candidate = approved["candidate"]
        value = approved["value"]
        alias = alias or approved.get("alias")
    if alias is None:
        alias = {
            "domain_name": domain_name,
            "alias_key": normalized_alias,
            "canonical_value_key": normalized_canonical,
        }
    return {"alias": alias, "candidate": candidate, "value": value}


def resolve_lookup_value(domain_name: str, raw_value: Optional[str]) -> Optional[str]:
    if raw_value is None:
        return None
    normalized = normalize_domain_key(raw_value)
    if not normalized:
        return None
    direct = lookup_domain_value(domain_name, normalized)
    if direct:
        return str(direct["value_key"])
    alias = lookup_domain_alias(domain_name, normalized)
    if alias:
        return str(alias["canonical_value_key"])
    return normalized


def resolve_taxonomy_value(
    domain_name: str,
    raw_value: Optional[str],
    *,
    source: str,
    source_ref: Optional[str] = None,
    reason: Optional[str] = None,
    confidence: float = 0.6,
    created_by: Optional[str] = None,
) -> Dict[str, Any]:
    domain = get_domain_definition(domain_name)
    if not domain:
        raise ValueError(f"unknown domain: {domain_name}")
    normalized = normalize_domain_key(str(raw_value or ""))
    if not normalized:
        default_value = domain.get("default_value_key")
        if default_value:
            return {
                "domain_name": domain_name,
                "raw_value": raw_value,
                "normalized_value_key": normalized,
                "value_key": str(default_value),
                "resolution": "default",
                "used_fallback": True,
                "candidate": None,
            }
        raise ValueError(f"{domain_name} requires a value")

    canonical = lookup_domain_value(domain_name, normalized)
    if canonical:
        return {
            "domain_name": domain_name,
            "raw_value": raw_value,
            "normalized_value_key": normalized,
            "value_key": str(canonical["value_key"]),
            "resolution": "canonical",
            "used_fallback": False,
            "candidate": None,
        }

    alias = lookup_domain_alias(domain_name, normalized)
    if alias:
        aliased = lookup_domain_value(domain_name, str(alias["canonical_value_key"]))
        value_key = str(aliased["value_key"]) if aliased else str(alias["canonical_value_key"])
        return {
            "domain_name": domain_name,
            "raw_value": raw_value,
            "normalized_value_key": normalized,
            "value_key": value_key,
            "resolution": "alias",
            "used_fallback": False,
            "candidate": None,
        }

    governance_mode = str(domain.get("governance_mode") or DOMAIN_GOVERNANCE_FIXED)
    if governance_mode == DOMAIN_GOVERNANCE_FIXED:
        raise ValueError(f"unknown fixed domain value for {domain_name}: {raw_value}")

    if governance_mode == DOMAIN_GOVERNANCE_AUTO_APPROVE:
        value = _create_domain_value(
            domain_name=domain_name,
            value_key=normalized,
            display_name=str(raw_value or normalized),
            description=reason,
            created_by=created_by,
            metadata={"source": source, "source_ref": source_ref},
        )
        return {
            "domain_name": domain_name,
            "raw_value": raw_value,
            "normalized_value_key": normalized,
            "value_key": str(value["value_key"]),
            "resolution": "auto_approved",
            "used_fallback": False,
            "candidate": None,
        }

    candidate = create_domain_candidate(
        domain_name=domain_name,
        proposed_value_key=str(raw_value or normalized),
        normalized_value_key=normalized,
        source=source,
        source_ref=source_ref,
        reason=reason,
        confidence=confidence,
        created_by=created_by,
        metadata={"raw_value": raw_value},
    )
    fallback = domain.get("default_value_key")
    if not fallback:
        raise ValueError(f"{domain_name} has no default fallback")
    return {
        "domain_name": domain_name,
        "raw_value": raw_value,
        "normalized_value_key": normalized,
        "value_key": str(fallback),
        "resolution": "candidate",
        "used_fallback": True,
        "candidate": candidate,
    }
