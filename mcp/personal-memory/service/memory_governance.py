"""Lifecycle, sensitivity, and disclosure heuristics for memory records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from service.constants import (
    DISCLOSURE_GENTLE,
    DISCLOSURE_INTERNAL_ONLY,
    DISCLOSURE_NORMAL,
    DISCLOSURE_USER_CONFIRM,
    LIFECYCLE_COLD,
    LIFECYCLE_CONFLICTED,
    LIFECYCLE_FRESH,
    LIFECYCLE_STABLE,
    LIFECYCLE_STALE,
    SENSITIVITY_NORMAL,
    SENSITIVITY_PUBLIC,
    SENSITIVITY_RESTRICTED,
    SENSITIVITY_SENSITIVE,
    STATUS_ACTIVE,
)


HEALTH_KEYWORDS = ("高血压", "血压", "糖尿病", "抑郁", "焦虑", "生病", "怀孕", "health")
RELATIONSHIP_KEYWORDS = ("对象", "伴侣", "家人", "朋友", "关系", "friend", "partner", "family")
PRIVACY_KEYWORDS = ("隐私", "秘密", "private", "secret")
PUBLIC_HINTS = ("favorite_", "preference", "规则", "rule", "project", "current_focus")


def _normalized_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(_normalized_text(item) for item in value)
    return str(value).strip().lower()


def _as_datetime(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def derive_memory_governance(item: Dict[str, Any]) -> Dict[str, str]:
    text = _normalized_text(
        [
            item.get("title"),
            item.get("content"),
            item.get("summary"),
            item.get("claim"),
            item.get("category"),
            item.get("attribute"),
            item.get("attribute_key"),
            item.get("subject"),
            item.get("subject_key"),
            item.get("tags"),
        ]
    )
    subject_key = _normalized_text(item.get("subject_key") or item.get("subject"))
    third_party = bool(subject_key and subject_key not in {"user", "self", "me"})
    has_health = any(token in text for token in HEALTH_KEYWORDS)
    has_relationship = any(token in text for token in RELATIONSHIP_KEYWORDS)
    has_privacy = any(token in text for token in PRIVACY_KEYWORDS)
    looks_public = any(token in text for token in PUBLIC_HINTS)

    if third_party and (has_health or has_privacy):
        return {
            "sensitivity_level": SENSITIVITY_RESTRICTED,
            "disclosure_policy": DISCLOSURE_INTERNAL_ONLY,
        }
    if has_health or has_relationship or has_privacy:
        return {
            "sensitivity_level": SENSITIVITY_SENSITIVE,
            "disclosure_policy": DISCLOSURE_GENTLE if not third_party else DISCLOSURE_USER_CONFIRM,
        }
    if looks_public:
        return {
            "sensitivity_level": SENSITIVITY_PUBLIC,
            "disclosure_policy": DISCLOSURE_NORMAL,
        }
    return {
        "sensitivity_level": SENSITIVITY_NORMAL,
        "disclosure_policy": DISCLOSURE_NORMAL,
    }


def derive_stability_score(item: Dict[str, Any]) -> float:
    confidence = float(item.get("confidence") or 0.0)
    explicit_bonus = 0.18 if item.get("is_explicit") else 0.0
    recall_bonus = min(int(item.get("recall_count") or 0), 3) * 0.12
    age_penalty = 0.0
    updated_at = _as_datetime(item.get("updated_at"))
    attribute_key = str(item.get("attribute_key") or "").lower()
    # 时效性强的属性使用更激进的衰减曲线
    TIME_SENSITIVE_ATTRS = ("current_goal", "current_project", "current_focus",
                            "current_status", "short_term")
    is_time_sensitive = any(attr in attribute_key for attr in TIME_SENSITIVE_ATTRS)
    if updated_at:
        age_days = max(0.0, (datetime.now(timezone.utc) - updated_at).days)
        if is_time_sensitive:
            if age_days >= 60:
                age_penalty = 0.40
            elif age_days >= 30:
                age_penalty = 0.25
            elif age_days >= 14:
                age_penalty = 0.12
        else:
            if age_days >= 120:
                age_penalty = 0.30
            elif age_days >= 60:
                age_penalty = 0.18
            elif age_days >= 45:
                age_penalty = 0.10
    return round(max(0.0, min(1.0, confidence + explicit_bonus + recall_bonus - age_penalty)), 4)


def derive_lifecycle_state(item: Dict[str, Any]) -> str:
    status = str(item.get("status") or STATUS_ACTIVE)
    if status != STATUS_ACTIVE:
        return str(item.get("lifecycle_state") or LIFECYCLE_STALE)
    if item.get("conflict_with_id"):
        return LIFECYCLE_CONFLICTED
    valid_to = _as_datetime(item.get("valid_to"))
    now = datetime.now(timezone.utc)
    if valid_to and valid_to < now:
        return LIFECYCLE_STALE

    updated_at = _as_datetime(item.get("updated_at")) or now
    age_days = max(0.0, (now - updated_at).days)
    recall_count = int(item.get("recall_count") or 0)
    confidence = float(item.get("confidence") or 0.0)
    is_explicit = bool(item.get("is_explicit"))
    stability_score = float(item.get("stability_score") or derive_stability_score(item))
    memory_type = str(item.get("memory_type") or "")

    if is_explicit and confidence >= 0.85:
        return LIFECYCLE_STABLE
    if recall_count >= 2 or stability_score >= 0.82:
        return LIFECYCLE_STABLE
    if age_days >= 120 and recall_count == 0 and not is_explicit:
        return LIFECYCLE_STALE
    if age_days >= 30 and recall_count == 0 and memory_type == "context":
        return LIFECYCLE_COLD
    if age_days >= 60 and recall_count == 0:
        return LIFECYCLE_COLD
    return LIFECYCLE_FRESH


def apply_memory_governance(item: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(item)
    # B2: 降低被替代或冲突记忆的置信度
    raw_confidence = float(payload.get("confidence") or 0.0)
    if payload.get("supersedes_id"):
        # 旧版本记忆（已被新版本取代）
        payload["confidence"] = min(raw_confidence, 0.35)
    elif payload.get("conflict_with_id"):
        # 存在冲突的记忆，置信度折半���较低值
        payload["confidence"] = min(raw_confidence, max(raw_confidence * 0.5, 0.35))
    payload["stability_score"] = float(payload.get("stability_score") or derive_stability_score(payload))
    payload["lifecycle_state"] = str(payload.get("lifecycle_state") or derive_lifecycle_state(payload))
    governance = derive_memory_governance(payload)
    payload["sensitivity_level"] = str(payload.get("sensitivity_level") or governance["sensitivity_level"])
    payload["disclosure_policy"] = str(payload.get("disclosure_policy") or governance["disclosure_policy"])
    return payload
