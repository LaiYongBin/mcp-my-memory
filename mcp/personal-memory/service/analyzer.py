"""Structured memory analysis for conversation turns."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Sequence
from urllib.request import Request, urlopen

from psycopg.types.json import Json

from service.constants import (
    ACTION_IGNORE,
    ACTION_LONG_TERM,
    ACTION_REVIEW,
    ACTION_WORKING_MEMORY,
    CONFLICT_COEXIST,
    CONFLICT_MERGE,
    CONFLICT_REPLACE,
    CONFLICT_REVIEW,
    DEFAULT_SESSION_KEY,
    EVIDENCE_EXPLICIT,
    EVIDENCE_OBSERVED,
    STATUS_ACTIVE,
    TIME_EPHEMERAL,
    TIME_LONG_TERM,
    TIME_MID_TERM,
    TIME_SHORT_TERM,
)
from service.db import get_conn, get_settings
from service.domain_registry import (
    DOMAIN_ATTRIBUTE_KEY,
    DOMAIN_CATEGORY,
    resolve_taxonomy_value,
)
from service.memory_governance import derive_memory_governance


SHORT_TERM_HINTS = [
    "今天",
    "明天",
    "最近",
    "当前",
    "目前",
    "先",
    "暂时",
    "这次",
    "这周",
    "本周",
]

SENSITIVE_HINTS = [
    "抑郁",
    "焦虑",
    "生病",
    "怀孕",
    "对象是不是",
    "爱不爱",
]

SELF_FACT_RISKY_KEYWORDS = [
    "抑郁",
    "焦虑",
    "生病",
    "怀孕",
    "政治",
    "宗教",
]


def _resolve_user(user_code: Optional[str]) -> str:
    return user_code or str(get_settings()["memory_user"])


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _contains_any(text: str, keywords: Sequence[str]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def analyzer_config() -> Dict[str, Any]:
    return {
        "api_key": os.environ.get("LYB_SKILL_MEMORY_ANALYZE_API_KEY")
        or os.environ.get("LYB_SKILL_MEMORY_EMBED_API_KEY"),
        "base_url": os.environ.get(
            "LYB_SKILL_MEMORY_ANALYZE_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
        "model": os.environ.get("LYB_SKILL_MEMORY_ANALYZE_MODEL", "qwen-plus-latest"),
        "timeout": int(os.environ.get("LYB_SKILL_MEMORY_ANALYZE_TIMEOUT", "90")),
    }


def analyzer_enabled() -> bool:
    config = analyzer_config()
    return bool(config["api_key"] and config["model"])


def _recent_memory_context(user_code: str, limit: int = 12) -> List[Dict[str, Any]]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, memory_type, title, content, subject_key, attribute_key,
                   value_text, conflict_scope, confidence, status, updated_at
            FROM memory_record
            WHERE user_code = %s
              AND deleted_at IS NULL
              AND status = %s
            ORDER BY updated_at DESC
            LIMIT %s
            """,
            (user_code, STATUS_ACTIVE, limit),
        )
        return [dict(row) for row in cur.fetchall()]


def _extract_json(text: str) -> str:
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\[.*\]|\{.*\})\s*```", stripped, re.S)
    if fenced:
        return fenced.group(1)
    bracket = re.search(r"(\[.*\])", stripped, re.S)
    if bracket:
        return bracket.group(1)
    brace = re.search(r"(\{.*\})", stripped, re.S)
    if brace:
        return brace.group(1)
    return stripped


def _analysis_prompt(user_text: str, assistant_text: str, recent_memories: List[Dict[str, Any]]) -> str:
    schema = [
        {
            "category": "memory category",
            "subject": "user / partner / project / preference / context",
            "related_subject": "optional second entity key when the claim links two entities",
            "attribute": "favorite_drink / favorite_food / personality_trait / possible_role / domain_interest / current_focus / current_goal / collaboration_rule / life_status / relationship_fact",
            "value": "atomic value only",
            "claim": "natural-language claim",
            "rationale": "why this is worth remembering",
            "evidence_type": "explicit | observed | inferred",
            "time_scope": "long_term | mid_term | short_term | ephemeral",
            "action": "long_term | working_memory | review | ignore",
            "confidence": 0.0,
            "conflict_scope": "subject.attribute if applicable, else null",
            "conflict_mode": "coexist | replace | review | merge",
            "tags": ["optional", "tags"],
        }
    ]
    return (
        "你是个人记忆分析器。请从下面这轮对话里提取真正值得记忆的点。\n"
        "不要按固定领域关键词判断，要基于语义理解。\n"
        "要求：\n"
        "1. 只提取值得保存的记忆点。\n"
        "2. 每个记忆点必须槽位化，至少包含 subject/attribute/value。attribute 要优先使用稳定的通用槽位名，不要每轮发明新槽位。\n"
        "3. 优先使用这些通用槽位：favorite_drink、favorite_food、personality_trait、possible_role、domain_interest、current_focus、current_goal、collaboration_rule、life_status、relationship_fact。\n"
        "4. 如果一句话明确描述双实体关系，例如“我的朋友小王在 memory mcp 项目里负责后端”，必须保留主实体为 subject，并把另一个实体填到 related_subject。只有明确存在两个实体时才填写 related_subject。\n"
        "5. 双实体关系里，attribute 优先使用 relationship_fact，value 只保留关系本身，例如“负责后端”或“参与项目”。\n"
        "6. 如果和旧记忆是同一槽位但值互斥，优先用 conflict_mode=replace 或 review。\n"
        "7. 如果只是新的不同槽位，例如 favorite_drink 和 favorite_food，必须 coexist，不要误判冲突。\n"
        "8. 对职业、年龄、性别、人格等推断要谨慎；没有足够证据时用 observed 或 inferred，不要冒充 explicit。\n"
        "9. 如果一轮对话体现出高层稳定信号，例如反复出现的技术工作、长期偏好、人格倾向，请额外给出 domain_interest 或 possible_role / personality_trait 这类可累积证据。\n"
        "10. 推断型结论应尽量描述成可累积证据的记忆点，而不是一次就下定论。\n"
        "11. 如果只是当前一次性需求，放 working_memory。\n"
        "12. value 要尽量规范化、短语化，去掉时间词，方便跨轮累积。\n"
        "13. 对偏好、性格、关系这类信息，是否长期化应由语义判断决定，不要依赖固定句式。\n"
        "14. 如果用户只是弱表达、一次性表达、临时情绪，优先降低 confidence 或改成 ignore/working_memory。\n"
        "15. 输出必须是 JSON 数组，不要任何额外说明。\n\n"
        f"当前用户输入:\n{user_text}\n\n"
        f"当前助手回复:\n{assistant_text}\n\n"
        f"最近已有记忆:\n{json.dumps(recent_memories, ensure_ascii=False, default=str)}\n\n"
        f"输出 schema 示例:\n{json.dumps(schema, ensure_ascii=False)}"
    )


def _call_analyzer_model(prompt: str) -> List[Dict[str, Any]]:
    config = analyzer_config()
    base_url = str(config["base_url"]).rstrip("/")
    if not analyzer_enabled():
        return []
    request = Request(
        base_url + "/chat/completions",
        data=json.dumps(
            {
                "model": config["model"],
                "messages": [
                    {"role": "system", "content": "你是严谨的结构化个人记忆分析器。"},
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
    with urlopen(request, timeout=int(config["timeout"])) as response:
        payload = json.loads(response.read().decode("utf-8"))
    content = payload["choices"][0]["message"]["content"]
    parsed = json.loads(_extract_json(content))
    if isinstance(parsed, dict):
        parsed = parsed.get("items") or parsed.get("data") or []
    return parsed if isinstance(parsed, list) else []


ATTRIBUTE_ALIASES = {
    "self_description": "personality_trait",
    "personality": "personality_trait",
    "trait": "personality_trait",
    "possible_job": "possible_role",
    "likely_role": "possible_role",
    "role": "possible_role",
    "topic_interest": "domain_interest",
    "current_technical_focus": "current_focus",
    "current_learning_focus": "current_focus",
    "current_performance_focus": "current_focus",
}


def _canonical_attribute(attribute: str) -> str:
    cleaned = str(attribute or "").strip()
    if not cleaned:
        return cleaned
    if cleaned in ATTRIBUTE_ALIASES:
        return ATTRIBUTE_ALIASES[cleaned]
    if cleaned.startswith("current_") and cleaned.endswith("_focus"):
        return "current_focus"
    return cleaned


def build_analysis_item(
    *,
    category: str,
    subject: str,
    related_subject: Optional[str] = None,
    attribute: str,
    value: str,
    claim: str,
    rationale: str,
    evidence_type: str,
    time_scope: str,
    action: str,
    confidence: float,
    conflict_scope: Optional[str] = None,
    conflict_mode: str = CONFLICT_COEXIST,
    tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "category": category,
        "subject": subject,
        "related_subject": related_subject,
        "attribute": attribute,
        "value": value,
        "claim": claim,
        "rationale": rationale,
        "evidence_type": evidence_type,
        "time_scope": time_scope,
        "action": action,
        "confidence": confidence,
        "conflict_scope": conflict_scope,
        "conflict_mode": conflict_mode,
        "tags": tags or [],
    }


def _normalize_subject_key(prefix: str, raw_value: str) -> Optional[str]:
    cleaned = re.sub(r"[\s\-./]+", "_", str(raw_value or "").strip().lower())
    cleaned = re.sub(r"[^\w\u4e00-\u9fff_]+", "", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned:
        return None
    return f"{prefix}_{cleaned}"


def _explicit_relationship_analysis(user_text: str) -> List[Dict[str, Any]]:
    cleaned = _clean(user_text)
    patterns = [
        (r"我(?:的)?朋友(?P<person>[一-龥]{1,4})在(?P<project>[\w\s\-]{2,40}?)项目(?:里|中)?(?P<detail>.*)", "friend"),
        (r"我(?:的)?对象(?P<person>[一-龥]{1,4})在(?P<project>[\w\s\-]{2,40}?)项目(?:里|中)?(?P<detail>.*)", "partner"),
        (r"我(?:的)?同事(?P<person>[一-龥]{1,4})在(?P<project>[\w\s\-]{2,40}?)项目(?:里|中)?(?P<detail>.*)", "team"),
    ]
    for pattern, relation_prefix in patterns:
        match = re.search(pattern, cleaned)
        if not match:
            continue
        subject = _normalize_subject_key(relation_prefix, match.group("person"))
        related_subject = _normalize_subject_key("project", match.group("project"))
        if not subject or not related_subject:
            continue
        detail = str(match.group("detail") or "").strip("。！？!?,， ")
        value = detail or f"参与{match.group('project').strip()}项目"
        return [
            build_analysis_item(
                category="relationship",
                subject=subject,
                related_subject=related_subject,
                attribute="relationship_fact",
                value=value,
                claim=cleaned,
                rationale="用户明确描述了两个实体之间的关系，适合作为关系记忆保留。",
                evidence_type=EVIDENCE_EXPLICIT,
                time_scope=TIME_LONG_TERM,
                action=ACTION_LONG_TERM,
                confidence=0.78,
                conflict_scope=None,
                conflict_mode=CONFLICT_COEXIST,
                tags=["relationship", "entity-link", "conservative-fallback"],
            )
        ]
    return []


def _fallback_analysis(user_text: str) -> List[Dict[str, Any]]:
    cleaned = _clean(user_text)
    if not cleaned:
        return []
    relationship_items = _explicit_relationship_analysis(cleaned)
    if relationship_items:
        return relationship_items
    favorite_match = re.search(r"我最喜欢(?:(喝|吃|用|看|听|去|做))?(?P<value>.+)", cleaned)
    if favorite_match:
        verb = favorite_match.group(1) or ""
        value = favorite_match.group("value").strip("。！？!?,， ")
        attribute_map = {
            "喝": "favorite_drink",
            "吃": "favorite_food",
            "用": "favorite_tool",
            "看": "favorite_content",
            "听": "favorite_audio",
            "去": "favorite_place",
            "做": "favorite_activity",
        }
        attribute = attribute_map.get(verb, "favorite_preference")
        return [
            build_analysis_item(
                category="preference",
                subject="user",
                attribute=attribute,
                value=value,
                claim=value,
                rationale="用户明确表达了最喜欢的对象，适合作为长期偏好记忆。",
                evidence_type=EVIDENCE_EXPLICIT,
                time_scope=TIME_LONG_TERM,
                action=ACTION_LONG_TERM,
                confidence=0.9,
                conflict_scope=f"user.{attribute}",
                conflict_mode=CONFLICT_REPLACE,
                tags=["preference", "favorite"],
            )
        ]
    preference_match = re.search(r"我(?P<polarity>不喜欢|喜欢|习惯)(?:(喝|吃|用|看|听|做))?(?P<value>.+)", cleaned)
    if preference_match:
        polarity = preference_match.group("polarity")
        verb = preference_match.group(2) or ""
        value = preference_match.group("value").strip("。！？!?,， ")
        base_map = {
            "喝": "drink_preference",
            "吃": "food_preference",
            "用": "tool_preference",
            "看": "content_preference",
            "听": "audio_preference",
            "做": "activity_preference",
        }
        attribute = base_map.get(verb, "general_preference")
        if polarity == "不喜欢":
            attribute = "dislike_" + attribute
        elif polarity == "习惯":
            attribute = "habit_" + attribute
        return [
            build_analysis_item(
                category="preference",
                subject="user",
                attribute=attribute,
                value=value,
                claim=value,
                rationale="用户明确表达了稳定偏好或习惯。",
                evidence_type=EVIDENCE_EXPLICIT,
                time_scope=TIME_LONG_TERM,
                action=ACTION_LONG_TERM,
                confidence=0.82,
                conflict_scope=None if polarity != "习惯" else f"user.{attribute}",
                conflict_mode=CONFLICT_COEXIST if polarity != "习惯" else CONFLICT_MERGE,
                tags=["preference"],
            )
        ]
    if _contains_any(cleaned, SENSITIVE_HINTS):
        return [
            build_analysis_item(
                category="sensitive_state",
                subject="user",
                attribute="state",
                value=cleaned,
                claim=cleaned,
                rationale="这条消息包含敏感或模糊的状态信息，需要确认后再长期化。",
                evidence_type=EVIDENCE_EXPLICIT,
                time_scope=TIME_SHORT_TERM,
                action=ACTION_REVIEW,
                confidence=0.45,
                conflict_scope="user.state",
                conflict_mode=CONFLICT_REVIEW,
                tags=["sensitive"],
            )
        ]
    if _contains_any(cleaned, SHORT_TERM_HINTS):
        return [
            build_analysis_item(
                category="current_goal",
                subject="user",
                attribute="current_focus",
                value=cleaned,
                claim=cleaned,
                rationale="这条消息更像短期上下文或当前任务。",
                evidence_type=EVIDENCE_EXPLICIT,
                time_scope=TIME_SHORT_TERM,
                action=ACTION_WORKING_MEMORY,
                confidence=0.75,
                conflict_scope="user.current_focus",
                conflict_mode=CONFLICT_REPLACE,
                tags=["short-term"],
            )
        ]
    return [
        build_analysis_item(
            category="ephemeral",
            subject="user",
            attribute="ephemeral",
            value=cleaned,
            claim=cleaned,
            rationale="分析器不可用时，非显式记忆场景保持保守，不自动长期化。",
            evidence_type=EVIDENCE_OBSERVED,
            time_scope=TIME_EPHEMERAL,
            action=ACTION_IGNORE,
            confidence=0.35,
            conflict_scope=None,
            conflict_mode=CONFLICT_COEXIST,
            tags=["ephemeral", "conservative-fallback"],
        )
    ]


def _normalize_item(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    subject = str(item.get("subject") or "").strip() or "user"
    related_subject = str(item.get("related_subject") or item.get("target_subject") or "").strip() or None
    attribute = _canonical_attribute(str(item.get("attribute") or "").strip())
    value = str(item.get("value") or "").strip()
    claim = str(item.get("claim") or value).strip()
    if not attribute or not value or not claim:
        return None
    conflict_scope = item.get("conflict_scope")
    if not conflict_scope and attribute:
        conflict_scope = f"{subject}.{attribute}"
    return build_analysis_item(
        category=str(item.get("category") or "generic_memory").strip() or "generic_memory",
        subject=subject,
        related_subject=related_subject,
        attribute=attribute,
        value=value,
        claim=claim,
        rationale=str(item.get("rationale") or "来自当前对话的记忆分析结果。").strip(),
        evidence_type=str(item.get("evidence_type") or EVIDENCE_OBSERVED),
        time_scope=str(item.get("time_scope") or TIME_MID_TERM),
        action=str(item.get("action") or ACTION_WORKING_MEMORY),
        confidence=float(item.get("confidence") or 0.5),
        conflict_scope=str(conflict_scope) if conflict_scope else None,
        conflict_mode=str(item.get("conflict_mode") or CONFLICT_COEXIST),
        tags=list(item.get("tags") or []),
    )


def analyze_turn(
    *,
    user_text: str,
    assistant_text: str = "",
    user_code: Optional[str] = None,
    session_key: str = DEFAULT_SESSION_KEY,
) -> List[Dict[str, Any]]:
    resolved_user = _resolve_user(user_code)
    cleaned = _clean(user_text)
    if not cleaned:
        return []

    if analyzer_enabled():
        try:
            prompt = _analysis_prompt(
                user_text=cleaned,
                assistant_text=_clean(assistant_text),
                recent_memories=_recent_memory_context(resolved_user),
            )
            parsed = _call_analyzer_model(prompt)
            normalized = [_normalize_item(item) for item in parsed]
            items = [item for item in normalized if item]
            if items:
                return items
        except Exception:
            pass

    return _fallback_analysis(cleaned)


def save_analysis_results(
    *,
    user_code: str,
    session_key: str,
    source_event_id: Optional[int],
    items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    saved: List[Dict[str, Any]] = []
    if not items:
        return saved
    with get_conn() as conn, conn.cursor() as cur:
        for item in items:
            normalized_category = resolve_taxonomy_value(
                DOMAIN_CATEGORY,
                item.get("category") or "generic_memory",
                source="analyzer",
                source_ref=f"event:{source_event_id}" if source_event_id else None,
                reason="normalize analyzer category",
                confidence=float(item.get("confidence") or 0.5),
            )
            normalized_attribute = resolve_taxonomy_value(
                DOMAIN_ATTRIBUTE_KEY,
                item.get("attribute") or "memory",
                source="analyzer",
                source_ref=f"event:{source_event_id}" if source_event_id else None,
                reason="normalize analyzer attribute",
                confidence=float(item.get("confidence") or 0.5),
            )
            governance = derive_memory_governance(
                item
                | {
                    "category": normalized_category["value_key"],
                    "attribute": normalized_attribute["value_key"],
                }
            )
            cur.execute(
                """
                INSERT INTO memory_inference (
                    user_code, session_key, source_event_id, category, subject, related_subject, attribute, value, claim,
                    rationale, evidence_type, time_scope, action, confidence, conflict_scope,
                    conflict_mode, sensitivity_level, disclosure_policy, status, tags
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
                RETURNING id, user_code, session_key, source_event_id, category, subject, related_subject, attribute,
                          value, claim, rationale, evidence_type, time_scope, action, confidence,
                          conflict_scope, conflict_mode, sensitivity_level, disclosure_policy,
                          status, tags, created_at, updated_at
                """,
                (
                    user_code,
                    session_key,
                    source_event_id,
                    normalized_category["value_key"],
                    item["subject"],
                    item.get("related_subject"),
                    normalized_attribute["value_key"],
                    item["value"],
                    item["claim"],
                    item["rationale"],
                    item["evidence_type"],
                    item["time_scope"],
                    item["action"],
                    item["confidence"],
                    item.get("conflict_scope"),
                    item.get("conflict_mode", CONFLICT_COEXIST),
                    governance["sensitivity_level"],
                    governance["disclosure_policy"],
                    STATUS_ACTIVE,
                    Json(item.get("tags") or []),
                ),
            )
            row = cur.fetchone()
            saved.append(dict(row))
        conn.commit()
    return saved


def list_analysis_results(
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
            SELECT id, user_code, session_key, source_event_id, category, subject, related_subject, attribute,
                   value, claim, rationale, evidence_type, time_scope, action, confidence,
                   conflict_scope, conflict_mode, sensitivity_level, disclosure_policy,
                   status, tags, created_at, updated_at
            FROM memory_inference
            WHERE {where_sql}
            ORDER BY updated_at DESC, id DESC
            LIMIT %s
            """,
            params + [limit],
        )
        return [dict(row) for row in cur.fetchall()]


def mark_event_analyzed(event_ids: Sequence[int]) -> None:
    ids = [int(event_id) for event_id in event_ids if event_id]
    if not ids:
        return
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE conversation_turn
            SET analyzed_status = 'done',
                analyzed_at = now()
            WHERE id = ANY(%s)
            """,
            (ids,),
        )
        conn.commit()
