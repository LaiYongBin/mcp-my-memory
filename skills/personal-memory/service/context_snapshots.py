"""Session context snapshots for segment- and topic-level recall."""

from __future__ import annotations

import json
import re
from hashlib import md5
from typing import Any, Dict, List, Optional, Sequence
from urllib.request import Request, urlopen

from psycopg.types.json import Json

from service.analyzer import _extract_json, analyzer_config, analyzer_enabled, analyze_turn, save_analysis_results
from service.capture_cycle import _resolve_user, record_conversation_event, resolve_analysis_memory
from service.db import get_conn
from service.evidence import accumulate_evidence, evidence_supports_promotion, mark_evidence_promoted, promoted_confidence
from service.memory_ops import save_review_candidate


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _topic_key(text: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", "-", text.lower()).strip("-")
    if cleaned:
        return cleaned[:120]
    return md5(text.encode("utf-8")).hexdigest()[:16]


def _call_text_model(prompt: str) -> Dict[str, Any]:
    config = analyzer_config()
    base_url = str(config["base_url"]).rstrip("/")
    request = Request(
        base_url + "/chat/completions",
        data=json.dumps(
            {
                "model": config["model"],
                "messages": [
                    {"role": "system", "content": "你是严谨的会话摘要与上下文索引助手。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
            }
        ).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + str(config["api_key"]),
        },
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    content = payload["choices"][0]["message"]["content"]
    parsed = json.loads(_extract_json(content))
    if isinstance(parsed, list):
        return parsed[0] if parsed else {}
    return parsed if isinstance(parsed, dict) else {}


def _fallback_segment_summary(
    transcript: Sequence[Dict[str, Any]], topic_hint: Optional[str] = None
) -> Dict[str, Any]:
    user_turns = [_clean(str(item.get("content") or "")) for item in transcript if item.get("role") == "user"]
    assistant_turns = [_clean(str(item.get("content") or "")) for item in transcript if item.get("role") == "assistant"]
    topic = topic_hint or (user_turns[0][:24] if user_turns else "当前对话")
    key_points = [text for text in (user_turns + assistant_turns) if text][:6]
    open_questions = [text for text in key_points if any(token in text for token in ["?", "？", "为什么", "怎么"])]
    return {
        "topic": topic,
        "topic_key": _topic_key(topic),
        "summary": "；".join(key_points[:3])[:400] or topic,
        "user_view": "；".join(user_turns[:3])[:400],
        "assistant_view": "；".join(assistant_turns[:3])[:400],
        "key_points": key_points[:8],
        "open_questions": open_questions[:6],
    }


def _segment_summary_prompt(transcript: Sequence[Dict[str, Any]], topic_hint: Optional[str] = None) -> str:
    schema = {
        "topic": "本段对话主题",
        "topic_key": "稳定主题键，短一些",
        "summary": "本段摘要",
        "user_view": "用户的主要观点/需求",
        "assistant_view": "助手的主要判断/建议",
        "key_points": ["关键点"],
        "open_questions": ["仍未解决的问题"],
    }
    return (
        "请把下面一段对话整理成可检索的上下文摘要。"
        "要点：1. topic 用稳定主题，不要过细。"
        "2. summary 要覆盖这段对话的核心。"
        "3. user_view 总结用户当时在表达什么、怎么想。"
        "4. assistant_view 总结助手当时的主要判断或建议。"
        "5. key_points 保留关键观点。"
        "6. open_questions 只保留仍值得追问的问题。"
        "7. 只输出 JSON 对象。\n\n"
        f"topic_hint: {topic_hint or ''}\n"
        f"transcript:\n{json.dumps(list(transcript), ensure_ascii=False, default=str)}\n\n"
        f"schema:\n{json.dumps(schema, ensure_ascii=False)}"
    )


def _merge_topic_prompt(existing: Dict[str, Any], segment: Dict[str, Any]) -> str:
    schema = {
        "topic": "归并后主题",
        "topic_key": "稳定主题键",
        "summary": "主题级摘要",
        "user_view": "用户在这个大话题里的主要立场/关注点",
        "assistant_view": "助手在这个大话题里的主要判断/建议",
        "key_points": ["关键点"],
        "open_questions": ["未决问题"],
    }
    return (
        "请把已有主题摘要和新片段摘要合并成一个更高层的主题摘要。"
        "要去重、保留核心、不要只是简单拼接。"
        "只输出 JSON 对象。\n\n"
        f"existing:\n{json.dumps(existing, ensure_ascii=False, default=str)}\n\n"
        f"segment:\n{json.dumps(segment, ensure_ascii=False, default=str)}\n\n"
        f"schema:\n{json.dumps(schema, ensure_ascii=False)}"
    )


def summarize_segment(
    transcript: Sequence[Dict[str, Any]], topic_hint: Optional[str] = None
) -> Dict[str, Any]:
    if not transcript:
        return _fallback_segment_summary([], topic_hint)
    if analyzer_enabled():
        try:
            parsed = _call_text_model(_segment_summary_prompt(transcript, topic_hint))
            if parsed.get("topic") and parsed.get("summary"):
                parsed["topic_key"] = parsed.get("topic_key") or _topic_key(str(parsed["topic"]))
                parsed["key_points"] = list(parsed.get("key_points") or [])
                parsed["open_questions"] = list(parsed.get("open_questions") or [])
                return parsed
        except Exception:
            pass
    return _fallback_segment_summary(transcript, topic_hint)


def merge_topic_summary(existing: Optional[Dict[str, Any]], segment: Dict[str, Any]) -> Dict[str, Any]:
    if not existing:
        return {
            "topic": segment["topic"],
            "topic_key": segment["topic_key"],
            "summary": segment["summary"],
            "user_view": segment.get("user_view"),
            "assistant_view": segment.get("assistant_view"),
            "key_points": list(segment.get("key_points") or []),
            "open_questions": list(segment.get("open_questions") or []),
        }
    if analyzer_enabled():
        try:
            parsed = _call_text_model(_merge_topic_prompt(existing, segment))
            if parsed.get("topic") and parsed.get("summary"):
                parsed["topic_key"] = parsed.get("topic_key") or existing.get("topic_key") or segment["topic_key"]
                parsed["key_points"] = list(parsed.get("key_points") or [])
                parsed["open_questions"] = list(parsed.get("open_questions") or [])
                return parsed
        except Exception:
            pass
    key_points = list(dict.fromkeys(list(existing.get("key_points") or []) + list(segment.get("key_points") or [])))
    open_questions = list(
        dict.fromkeys(list(existing.get("open_questions") or []) + list(segment.get("open_questions") or []))
    )
    return {
        "topic": existing.get("topic") or segment["topic"],
        "topic_key": existing.get("topic_key") or segment["topic_key"],
        "summary": " ".join(
            part for part in [existing.get("summary"), segment.get("summary")] if str(part or "").strip()
        )[:600],
        "user_view": " ".join(
            part for part in [existing.get("user_view"), segment.get("user_view")] if str(part or "").strip()
        )[:600],
        "assistant_view": " ".join(
            part
            for part in [existing.get("assistant_view"), segment.get("assistant_view")]
            if str(part or "").strip()
        )[:600],
        "key_points": key_points[:12],
        "open_questions": open_questions[:12],
    }


def list_session_events(
    *, user_code: Optional[str] = None, session_key: str, limit: int = 200
) -> List[Dict[str, Any]]:
    resolved_user = _resolve_user(user_code)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, user_code, session_key, event_type, role, content, source_ref, created_at
            FROM conversation_event
            WHERE user_code = %s
              AND session_key = %s
            ORDER BY created_at ASC, id ASC
            LIMIT %s
            """,
            (resolved_user, session_key, limit),
        )
        return [dict(row) for row in cur.fetchall()]


def _save_snapshot(payload: Dict[str, Any]) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO conversation_context_snapshot (
                user_code, session_key, snapshot_level, topic_key, topic, summary,
                user_view, assistant_view, key_points, open_questions, source_event_ids,
                parent_snapshot_id, turn_count, started_at, ended_at, source_ref, status
            ) VALUES (
                %(user_code)s, %(session_key)s, %(snapshot_level)s, %(topic_key)s, %(topic)s, %(summary)s,
                %(user_view)s, %(assistant_view)s, %(key_points)s, %(open_questions)s, %(source_event_ids)s,
                %(parent_snapshot_id)s, %(turn_count)s, %(started_at)s, %(ended_at)s, %(source_ref)s, %(status)s
            )
            RETURNING id, user_code, session_key, snapshot_level, topic_key, topic, summary,
                      user_view, assistant_view, key_points, open_questions, source_event_ids,
                      parent_snapshot_id, turn_count, started_at, ended_at, source_ref,
                      status, created_at, updated_at
            """,
            payload
            | {
                "key_points": Json(payload.get("key_points") or []),
                "open_questions": Json(payload.get("open_questions") or []),
                "source_event_ids": Json(payload.get("source_event_ids") or []),
            },
        )
        row = cur.fetchone()
        conn.commit()
        return dict(row)


def _latest_topic_snapshot(*, user_code: str, session_key: str, topic_key: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, user_code, session_key, snapshot_level, topic_key, topic, summary,
                   user_view, assistant_view, key_points, open_questions, source_event_ids,
                   parent_snapshot_id, turn_count, started_at, ended_at, source_ref,
                   status, created_at, updated_at
            FROM conversation_context_snapshot
            WHERE user_code = %s
              AND session_key = %s
              AND snapshot_level = 'topic'
              AND topic_key = %s
              AND status = 'active'
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (user_code, session_key, topic_key),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _update_topic_snapshot(snapshot_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE conversation_context_snapshot
            SET topic = %(topic)s,
                summary = %(summary)s,
                user_view = %(user_view)s,
                assistant_view = %(assistant_view)s,
                key_points = %(key_points)s,
                open_questions = %(open_questions)s,
                source_event_ids = %(source_event_ids)s,
                turn_count = %(turn_count)s,
                started_at = %(started_at)s,
                ended_at = %(ended_at)s,
                source_ref = %(source_ref)s,
                updated_at = now()
            WHERE id = %(id)s
            RETURNING id, user_code, session_key, snapshot_level, topic_key, topic, summary,
                      user_view, assistant_view, key_points, open_questions, source_event_ids,
                      parent_snapshot_id, turn_count, started_at, ended_at, source_ref,
                      status, created_at, updated_at
            """,
            payload
            | {
                "id": snapshot_id,
                "key_points": Json(payload.get("key_points") or []),
                "open_questions": Json(payload.get("open_questions") or []),
                "source_event_ids": Json(payload.get("source_event_ids") or []),
            },
        )
        row = cur.fetchone()
        conn.commit()
        return dict(row)


def _persist_session_memory_from_snapshot(
    *,
    user_code: str,
    session_key: str,
    segment: Dict[str, Any],
    source_event_id: Optional[int],
) -> Dict[str, Any]:
    user_text = "\n".join(
        part for part in [segment.get("user_view"), "；".join(segment.get("key_points") or [])] if str(part or "").strip()
    )
    assistant_text = str(segment.get("assistant_view") or segment.get("summary") or "")
    items = analyze_turn(
        user_text=user_text,
        assistant_text=assistant_text,
        user_code=user_code,
        session_key=session_key,
    )
    analysis_results = save_analysis_results(
        user_code=user_code,
        session_key=session_key,
        source_event_id=source_event_id,
        items=items,
    )
    persisted = []
    review_items = []
    evidence_items = []
    for item in analysis_results:
        action = item.get("action")
        claim = str(item.get("claim") or "").strip()
        confidence = float(item.get("confidence") or 0.5)
        category = str(item.get("category") or "analysis")
        tags = list(item.get("tags") or [])
        if action != "long_term" or not claim:
            continue
        evidence = accumulate_evidence(user_code=user_code, item=item)
        if evidence:
            evidence_items.append(evidence)
        if evidence_supports_promotion(item, evidence):
            promoted_item = item.copy()
            promoted_item["confidence"] = promoted_confidence(item, evidence)
            resolved = resolve_analysis_memory(promoted_item, user_code)
            memory_payload = resolved.get("memory")
            if memory_payload:
                persisted.append(resolved)
                memory_id = memory_payload.get("id") if isinstance(memory_payload, dict) else None
                if evidence and memory_id:
                    mark_evidence_promoted(int(evidence["id"]), int(memory_id))
            elif resolved.get("resolution") == "needs-review":
                review_items.append(
                    save_review_candidate(
                        user_code=user_code,
                        source_text=user_text,
                        candidate={
                            "title": "待确认候选: " + claim[:60],
                            "content": claim,
                            "memory_type": "context",
                            "reason": "session-context-review:" + category,
                            "confidence": confidence,
                            "tags": list(dict.fromkeys(tags + ["context-review"])),
                            "status": "pending",
                        },
                    )
                )
    return {
        "analysis_results": analysis_results,
        "analysis_result_count": len(analysis_results),
        "persisted": persisted,
        "persisted_count": len(persisted),
        "review_candidates": review_items,
        "review_candidate_count": len(review_items),
        "evidence": evidence_items,
        "evidence_count": len(evidence_items),
    }


def sync_session_context(
    *,
    session_key: str,
    turns: Optional[Sequence[Dict[str, Any]]] = None,
    user_code: Optional[str] = None,
    topic_hint: Optional[str] = None,
    source_ref: Optional[str] = None,
    extract_memory: bool = False,
) -> Dict[str, Any]:
    resolved_user = _resolve_user(user_code)
    events: List[Dict[str, Any]] = []
    if turns:
        for turn in turns:
            role = str(turn.get("role") or "").strip()
            content = str(turn.get("content") or "").strip()
            if role not in {"user", "assistant"} or not content:
                continue
            event = record_conversation_event(
                user_code=resolved_user,
                session_key=session_key,
                role=role,
                content=content,
                source_ref=source_ref,
                event_type="session_sync",
            )
            if event:
                events.append(event)
    else:
        events = list_session_events(user_code=resolved_user, session_key=session_key)

    transcript = [{"role": row["role"], "content": row["content"]} for row in events]
    segment = summarize_segment(transcript, topic_hint)
    started_at = events[0]["created_at"] if events else None
    ended_at = events[-1]["created_at"] if events else None
    segment_row = _save_snapshot(
        {
            "user_code": resolved_user,
            "session_key": session_key,
            "snapshot_level": "segment",
            "topic_key": segment["topic_key"],
            "topic": segment["topic"],
            "summary": segment["summary"],
            "user_view": segment.get("user_view"),
            "assistant_view": segment.get("assistant_view"),
            "key_points": segment.get("key_points") or [],
            "open_questions": segment.get("open_questions") or [],
            "source_event_ids": [int(row["id"]) for row in events if row.get("id")],
            "parent_snapshot_id": None,
            "turn_count": len(events),
            "started_at": started_at,
            "ended_at": ended_at,
            "source_ref": source_ref,
            "status": "active",
        }
    )

    existing_topic = _latest_topic_snapshot(
        user_code=resolved_user,
        session_key=session_key,
        topic_key=segment["topic_key"],
    )
    merged_topic = merge_topic_summary(existing_topic, segment)
    topic_payload = {
        "user_code": resolved_user,
        "session_key": session_key,
        "snapshot_level": "topic",
        "topic_key": merged_topic["topic_key"],
        "topic": merged_topic["topic"],
        "summary": merged_topic["summary"],
        "user_view": merged_topic.get("user_view"),
        "assistant_view": merged_topic.get("assistant_view"),
        "key_points": merged_topic.get("key_points") or [],
        "open_questions": merged_topic.get("open_questions") or [],
        "source_event_ids": list(
            dict.fromkeys(
                list(existing_topic.get("source_event_ids") or []) + [int(row["id"]) for row in events if row.get("id")]
            )
        )
        if existing_topic
        else [int(row["id"]) for row in events if row.get("id")],
        "turn_count": int(existing_topic.get("turn_count") or 0) + len(events) if existing_topic else len(events),
        "started_at": existing_topic.get("started_at") if existing_topic and existing_topic.get("started_at") else started_at,
        "ended_at": ended_at or (existing_topic.get("ended_at") if existing_topic else None),
        "source_ref": source_ref,
    }
    if existing_topic:
        topic_row = _update_topic_snapshot(int(existing_topic["id"]), topic_payload)
    else:
        topic_row = _save_snapshot(
            topic_payload
            | {
                "parent_snapshot_id": int(segment_row["id"]),
                "status": "active",
            }
        )

    memory_sync = None
    if extract_memory:
        memory_sync = _persist_session_memory_from_snapshot(
            user_code=resolved_user,
            session_key=session_key,
            segment=segment,
            source_event_id=int(events[-1]["id"]) if events else None,
        )

    return {
        "event_count": len(events),
        "segment_snapshot": segment_row,
        "topic_snapshot": topic_row,
        "memory_sync": memory_sync,
    }


def search_context_snapshots(
    *,
    query: str = "",
    user_code: Optional[str] = None,
    session_key: Optional[str] = None,
    snapshot_level: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    resolved_user = _resolve_user(user_code)
    conditions = ["user_code = %s", "status = 'active'"]
    params: List[Any] = [resolved_user]
    if session_key:
        conditions.append("session_key = %s")
        params.append(session_key)
    if snapshot_level:
        conditions.append("snapshot_level = %s")
        params.append(snapshot_level)
    if query.strip():
        tokens = [token for token in re.split(r"\s+", query.strip()) if token]
        for token in tokens:
            like = "%" + token + "%"
            conditions.append(
                """
                (
                    topic ILIKE %s
                    OR summary ILIKE %s
                    OR coalesce(user_view, '') ILIKE %s
                    OR coalesce(assistant_view, '') ILIKE %s
                )
                """
            )
            params.extend([like, like, like, like])
    where_sql = " AND ".join(conditions)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id, user_code, session_key, snapshot_level, topic_key, topic, summary,
                   user_view, assistant_view, key_points, open_questions, source_event_ids,
                   parent_snapshot_id, turn_count, started_at, ended_at, source_ref,
                   status, created_at, updated_at
            FROM conversation_context_snapshot
            WHERE {where_sql}
            ORDER BY ended_at DESC NULLS LAST, updated_at DESC, id DESC
            LIMIT %s
            """,
            params + [limit],
        )
        return [dict(row) for row in cur.fetchall()]
