"""Persistent entity profiles and relationship edges derived from memories."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from psycopg.types.json import Json

from service.db import get_conn, get_settings
from service.entity_memory import summarize_entities_from_memories


def _resolve_user(user_code: Optional[str]) -> str:
    return user_code or str(get_settings()["memory_user"])


def infer_relation_type(subject_key: str) -> str:
    cleaned = str(subject_key or "").strip().lower()
    for prefix in ("friend", "partner", "family", "project", "team", "user"):
        if cleaned == prefix or cleaned.startswith(prefix + "_"):
            return prefix
    return "entity"


def _relationship_semantic(item: Dict[str, Any]) -> Optional[str]:
    text = " ".join(
        str(item.get(key) or "").strip()
        for key in ("value_text", "claim", "content", "title")
        if str(item.get(key) or "").strip()
    )
    if not text:
        return None
    if any(keyword in text for keyword in ("负责", "主导", "牵头", "owner", "owner of")):
        return "responsible_for"
    if any(keyword in text for keyword in ("一起", "合作", "协作", "共同", "配合")):
        return "collaborates_with"
    if any(keyword in text for keyword in ("参与", "加入", "在", "就职于", "任职于")):
        return "participates_in"
    if any(keyword in text for keyword in ("认识", "熟悉", "朋友", "同事")):
        return "knows"
    return None


def infer_edge_relation_type(item: Dict[str, Any]) -> str:
    semantic = _relationship_semantic(item)
    if semantic:
        return semantic
    related_subject_key = str(item.get("related_subject_key") or item.get("target_subject_key") or "").strip()
    if related_subject_key:
        return infer_relation_type(related_subject_key)
    subject_key = str(item.get("subject_key") or "").strip()
    if subject_key:
        return infer_relation_type(subject_key)
    return infer_relation_type(str(item.get("relation_type") or "entity"))


def infer_display_name(subject_key: str, memories: List[Dict[str, Any]]) -> str:
    for row in memories:
        text = " ".join(
            str(row.get(key) or "").strip() for key in ("title", "content", "value_text") if row.get(key)
        )
        match = re.search(
            r"(?:朋友|家人|对象|伴侣|同事|项目)([一-龥]{1,4}?)(?:有|在|是|最近|喜欢|正|刚|并|，|。|\s|$)",
            text,
        )
        if match:
            return match.group(1)
    cleaned = str(subject_key or "").strip()
    for prefix in ("friend_", "partner_", "family_", "project_", "team_", "user_"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
            break
    return cleaned.replace("_", " ").strip()


def _load_subject_memories(*, user_code: str, subject_key: str) -> List[Dict[str, Any]]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, user_code, subject_key, category, attribute_key, title, content,
                   related_subject_key, sensitivity_level, disclosure_policy, created_at, updated_at
            FROM memory_record
            WHERE user_code = %s
              AND subject_key = %s
              AND deleted_at IS NULL
              AND status = 'active'
            ORDER BY updated_at DESC, id DESC
            """,
            (user_code, subject_key),
        )
        return [dict(row) for row in cur.fetchall()]


def _load_related_reference_memories(*, user_code: str, subject_key: str) -> List[Dict[str, Any]]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, user_code, subject_key, related_subject_key, category, attribute_key, title, content,
                   sensitivity_level, disclosure_policy, created_at, updated_at
            FROM memory_record
            WHERE user_code = %s
              AND related_subject_key = %s
              AND deleted_at IS NULL
              AND status = 'active'
            ORDER BY updated_at DESC, id DESC
            """,
            (user_code, subject_key),
        )
        return [dict(row) for row in cur.fetchall()]


def refresh_entity_graph_for_subject(*, user_code: Optional[str], subject_key: Optional[str]) -> None:
    cleaned_subject = str(subject_key or "").strip()
    if not cleaned_subject:
        return
    resolved_user = _resolve_user(user_code)
    memories = _load_subject_memories(user_code=resolved_user, subject_key=cleaned_subject)
    related_refs = _load_related_reference_memories(user_code=resolved_user, subject_key=cleaned_subject)
    with get_conn() as conn, conn.cursor() as cur:
        if not memories and not related_refs:
            cur.execute(
                "DELETE FROM entity_edge WHERE user_code = %s AND source_subject_key = %s",
                (resolved_user, cleaned_subject),
            )
            cur.execute(
                "DELETE FROM entity_profile WHERE user_code = %s AND subject_key = %s",
                (resolved_user, cleaned_subject),
            )
            conn.commit()
            return
        if memories:
            profile = summarize_entities_from_memories(memories, limit=1)[0]
            latest_memory_id = next((row.get("id") for row in memories if row.get("id") is not None), None)
            display_name = infer_display_name(cleaned_subject, memories)
            memory_count = int(profile.get("memory_count") or len(memories))
            category_keys = Json(list(profile.get("categories") or []))
            attribute_keys = Json(list(profile.get("attribute_keys") or []))
            sensitivity_level = str(profile.get("sensitivity_level") or "normal")
            disclosure_policy = str(profile.get("disclosure_policy") or "normal")
            first_seen_at = min(row.get("created_at") for row in memories if row.get("created_at") is not None)
            last_seen_at = max((row.get("updated_at") or row.get("created_at")) for row in memories)
        else:
            latest_memory_id = next((row.get("id") for row in related_refs if row.get("id") is not None), None)
            display_name = infer_display_name(cleaned_subject, related_refs)
            memory_count = 0
            category_keys = Json([])
            attribute_keys = Json([])
            sensitivity_level = str(related_refs[0].get("sensitivity_level") or "normal")
            disclosure_policy = str(related_refs[0].get("disclosure_policy") or "normal")
            first_seen_at = min(row.get("created_at") for row in related_refs if row.get("created_at") is not None)
            last_seen_at = max((row.get("updated_at") or row.get("created_at")) for row in related_refs)
        cur.execute(
            """
            INSERT INTO entity_profile (
                user_code, subject_key, display_name, relation_type, memory_count,
                category_keys, attribute_keys, sensitivity_level, disclosure_policy,
                latest_memory_id, first_seen_at, last_seen_at, status
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, 'active'
            )
            ON CONFLICT (user_code, subject_key)
            DO UPDATE SET
                display_name = EXCLUDED.display_name,
                relation_type = EXCLUDED.relation_type,
                memory_count = EXCLUDED.memory_count,
                category_keys = EXCLUDED.category_keys,
                attribute_keys = EXCLUDED.attribute_keys,
                sensitivity_level = EXCLUDED.sensitivity_level,
                disclosure_policy = EXCLUDED.disclosure_policy,
                latest_memory_id = EXCLUDED.latest_memory_id,
                first_seen_at = EXCLUDED.first_seen_at,
                last_seen_at = EXCLUDED.last_seen_at,
                status = 'active',
                updated_at = now()
            """,
            (
                resolved_user,
                cleaned_subject,
                display_name,
                str((profile.get("relation_type") if memories else None) or infer_relation_type(cleaned_subject)),
                memory_count,
                category_keys,
                attribute_keys,
                sensitivity_level,
                disclosure_policy,
                latest_memory_id,
                first_seen_at,
                last_seen_at,
            ),
        )
        cur.execute(
            """
            DELETE FROM entity_edge
            WHERE user_code = %s
              AND target_subject_key = %s
              AND source_subject_key = 'user'
            """,
            (resolved_user, cleaned_subject),
        )
        if memories and cleaned_subject != "user":
            cur.execute(
                """
                INSERT INTO entity_edge (
                    user_code, source_subject_key, target_subject_key, relation_type,
                    evidence_count, sensitivity_level, disclosure_policy, latest_memory_id, status
                ) VALUES (
                    %s, 'user', %s, %s,
                    %s, %s, %s, %s, 'active'
                )
                """,
                (
                    resolved_user,
                    cleaned_subject,
                    str(profile.get("relation_type") or infer_relation_type(cleaned_subject)),
                    int(profile.get("memory_count") or len(memories)),
                    str(profile.get("sensitivity_level") or "normal"),
                    str(profile.get("disclosure_policy") or "normal"),
                    latest_memory_id,
                ),
            )
        cur.execute(
            """
            DELETE FROM entity_edge
            WHERE user_code = %s
              AND source_subject_key = %s
              AND target_subject_key <> 'user'
            """,
            (resolved_user, cleaned_subject),
        )
        for row in memories:
            related_subject_key = str(row.get("related_subject_key") or "").strip()
            if not related_subject_key or related_subject_key == cleaned_subject:
                continue
            cur.execute(
                """
                INSERT INTO entity_profile (
                    user_code, subject_key, display_name, relation_type, memory_count,
                    category_keys, attribute_keys, sensitivity_level, disclosure_policy,
                    latest_memory_id, first_seen_at, last_seen_at, status
                ) VALUES (
                    %s, %s, %s, %s, 0,
                    '[]'::jsonb, '[]'::jsonb, %s, %s,
                    %s, %s, %s, 'active'
                )
                ON CONFLICT (user_code, subject_key)
                DO UPDATE SET
                    display_name = COALESCE(entity_profile.display_name, EXCLUDED.display_name),
                    relation_type = COALESCE(entity_profile.relation_type, EXCLUDED.relation_type),
                    updated_at = now()
                """,
                (
                    resolved_user,
                    related_subject_key,
                    infer_display_name(related_subject_key, []),
                    infer_relation_type(related_subject_key),
                    str(row.get("sensitivity_level") or "normal"),
                    str(row.get("disclosure_policy") or "normal"),
                    row.get("id"),
                    row.get("created_at"),
                    row.get("updated_at") or row.get("created_at"),
                ),
            )
            cur.execute(
                """
                INSERT INTO entity_edge (
                    user_code, source_subject_key, target_subject_key, relation_type,
                    evidence_count, sensitivity_level, disclosure_policy, latest_memory_id, status
                ) VALUES (
                    %s, %s, %s, %s,
                    1, %s, %s, %s, 'active'
                )
                ON CONFLICT (user_code, source_subject_key, target_subject_key, relation_type, status)
                DO UPDATE SET
                    evidence_count = entity_edge.evidence_count + 1,
                    sensitivity_level = EXCLUDED.sensitivity_level,
                    disclosure_policy = EXCLUDED.disclosure_policy,
                    latest_memory_id = EXCLUDED.latest_memory_id,
                    updated_at = now()
                """,
                (
                    resolved_user,
                    cleaned_subject,
                    related_subject_key,
                    infer_edge_relation_type(
                        {
                            "subject_key": cleaned_subject,
                            "related_subject_key": related_subject_key,
                        }
                    ),
                    str(row.get("sensitivity_level") or "normal"),
                    str(row.get("disclosure_policy") or "normal"),
                    row.get("id"),
                ),
            )
        conn.commit()


def sync_entity_graph_for_memory(memory: Dict[str, Any]) -> None:
    if not memory:
        return
    refresh_entity_graph_for_subject(
        user_code=str(memory.get("user_code") or ""),
        subject_key=memory.get("subject_key"),
    )
    refresh_entity_graph_for_subject(
        user_code=str(memory.get("user_code") or ""),
        subject_key=memory.get("related_subject_key"),
    )


def rebuild_entity_graph(*, user_code: Optional[str] = None) -> Dict[str, Any]:
    resolved_user = _resolve_user(user_code)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT subject_key
            FROM memory_record
            WHERE user_code = %s
              AND deleted_at IS NULL
              AND status = 'active'
              AND subject_key IS NOT NULL
              AND subject_key <> ''
            UNION
            SELECT DISTINCT related_subject_key AS subject_key
            FROM memory_record
            WHERE user_code = %s
              AND deleted_at IS NULL
              AND status = 'active'
              AND related_subject_key IS NOT NULL
              AND related_subject_key <> ''
            ORDER BY subject_key ASC
            """,
            (resolved_user, resolved_user),
        )
        subject_keys = [str(row["subject_key"]) for row in cur.fetchall()]
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM entity_edge
            WHERE user_code = %s
              AND (
                  source_subject_key <> ALL(%s)
                  OR target_subject_key <> ALL(%s)
              )
            """,
            (resolved_user, subject_keys or [""], subject_keys or [""]),
        )
        cur.execute(
            """
            DELETE FROM entity_profile
            WHERE user_code = %s
              AND subject_key <> ALL(%s)
            """,
            (resolved_user, subject_keys or [""]),
        )
        conn.commit()
    for subject_key in subject_keys:
        refresh_entity_graph_for_subject(user_code=resolved_user, subject_key=subject_key)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS count FROM entity_profile WHERE user_code = %s AND status = 'active'",
            (resolved_user,),
        )
        profile_count = int(cur.fetchone()["count"])
        cur.execute(
            "SELECT count(*) AS count FROM entity_edge WHERE user_code = %s AND status = 'active'",
            (resolved_user,),
        )
        edge_count = int(cur.fetchone()["count"])
    return {
        "profile_count": profile_count,
        "edge_count": edge_count,
        "subject_keys": subject_keys,
    }


def search_entities(
    *,
    query: str = "",
    user_code: Optional[str] = None,
    subject_key: Optional[str] = None,
    include_archived: bool = False,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    resolved_user = _resolve_user(user_code)
    conditions = ["user_code = %s"]
    params: List[Any] = [resolved_user]
    if not include_archived:
        conditions.append("status = 'active'")
    if subject_key:
        conditions.append("subject_key = %s")
        params.append(subject_key)
    if query:
        like = f"%{query}%"
        conditions.append(
            """
            (
                subject_key ILIKE %s OR
                display_name ILIKE %s OR
                EXISTS (
                    SELECT 1
                    FROM memory_record m
                    WHERE m.user_code = entity_profile.user_code
                      AND m.subject_key = entity_profile.subject_key
                      AND m.deleted_at IS NULL
                      AND m.status = 'active'
                      AND (
                          m.title ILIKE %s OR
                          m.content ILIKE %s OR
                          COALESCE(m.value_text, '') ILIKE %s
                      )
                )
            )
            """
        )
        params.extend([like, like, like, like, like])
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id, user_code, subject_key, display_name, relation_type, memory_count,
                   category_keys, attribute_keys, sensitivity_level, disclosure_policy,
                   latest_memory_id, first_seen_at, last_seen_at, status, created_at, updated_at
            FROM entity_profile
            WHERE {' AND '.join(conditions)}
            ORDER BY memory_count DESC, updated_at DESC
            LIMIT %s
            """,
            params + [limit],
        )
        return [dict(row) for row in cur.fetchall()]


def search_entity_relationships(
    *,
    query: str = "",
    user_code: Optional[str] = None,
    subject_key: Optional[str] = None,
    include_archived: bool = False,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    resolved_user = _resolve_user(user_code)
    conditions = ["e.user_code = %s"]
    params: List[Any] = [resolved_user]
    if not include_archived:
        conditions.append("e.status = 'active'")
    if subject_key:
        conditions.append("(e.source_subject_key = %s OR e.target_subject_key = %s)")
        params.extend([subject_key, subject_key])
    if query:
        like = f"%{query}%"
        conditions.append(
            """
            (
                e.source_subject_key ILIKE %s OR
                e.target_subject_key ILIKE %s OR
                COALESCE(p.display_name, '') ILIKE %s OR
                e.relation_type ILIKE %s OR
                EXISTS (
                    SELECT 1
                    FROM memory_record m
                    WHERE m.user_code = e.user_code
                      AND m.subject_key = e.target_subject_key
                      AND m.deleted_at IS NULL
                      AND m.status = 'active'
                      AND (
                          m.title ILIKE %s OR
                          m.content ILIKE %s OR
                          COALESCE(m.value_text, '') ILIKE %s
                      )
                )
            )
            """
        )
        params.extend([like, like, like, like, like, like, like])
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT e.id, e.user_code, e.source_subject_key, e.target_subject_key, e.relation_type,
                   e.evidence_count, e.sensitivity_level, e.disclosure_policy, e.latest_memory_id,
                   e.status, e.created_at, e.updated_at,
                   p.display_name AS target_display_name,
                   p.memory_count AS target_memory_count
            FROM entity_edge e
            LEFT JOIN entity_profile p
              ON p.user_code = e.user_code
             AND p.subject_key = e.target_subject_key
            WHERE {' AND '.join(conditions)}
            ORDER BY e.evidence_count DESC, e.updated_at DESC
            LIMIT %s
            """,
            params + [limit],
        )
        return [dict(row) for row in cur.fetchall()]
