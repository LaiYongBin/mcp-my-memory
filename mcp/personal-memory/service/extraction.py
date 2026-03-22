"""Conservative candidate-memory extraction for explicit remember commands."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from service.constants import SOURCE_CONVERSATION, STATUS_ACTIVE, STATUS_PENDING


EXPLICIT_PATTERNS = [
    r"记住(?P<content>.+)",
    r"不要忘了(?P<content>.+)",
    r"以后都按这个来[:：]?(?P<content>.+)",
]

RISKY_KEYWORDS = [
    "生病",
    "抑郁",
    "焦虑",
    "怀孕",
    "对象是不是",
    "爱不爱",
    "讨厌我",
    "身份",
    "政治",
    "宗教",
]


def _build_candidate(
    *,
    text: str,
    memory_type: str,
    confidence: float,
    importance: int,
    is_explicit: bool,
    title_prefix: str,
    extra_fields: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    content = text.strip("。！？!?,， ")
    payload = {
        "title": f"{title_prefix}: {content[:60]}",
        "content": content,
        "summary": content[:240],
        "memory_type": memory_type,
        "confidence": confidence,
        "importance": importance,
        "is_explicit": is_explicit,
        "status": STATUS_ACTIVE,
        "tags": ["auto-captured"] if not is_explicit else ["explicit-memory"],
        "source_type": SOURCE_CONVERSATION,
    }
    if extra_fields:
        payload.update(extra_fields)
    return payload


def _build_review_candidate(
    *, text: str, reason: str, memory_type: str = "relationship"
) -> Dict[str, Any]:
    content = text.strip("。！？!?,， ")
    return {
        "title": "待确认候选: " + content[:60],
        "content": content,
        "memory_type": memory_type,
        "confidence": 0.35,
        "reason": reason,
        "tags": ["review-candidate"],
        "status": STATUS_PENDING,
    }


def extract_candidates(text: str) -> List[Dict[str, Any]]:
    stripped = text.strip()
    if not stripped:
        return []

    candidates: List[Dict[str, Any]] = []

    for pattern in EXPLICIT_PATTERNS:
        match = re.search(pattern, stripped)
        if match:
            content = match.group("content").strip()
            candidates.append(
                _build_candidate(
                    text=content,
                    memory_type="fact",
                    confidence=0.95,
                    importance=8,
                    is_explicit=True,
                    title_prefix="长期记忆",
                )
            )
            return candidates

    return candidates


def extract_review_candidates(text: str) -> List[Dict[str, Any]]:
    stripped = text.strip()
    if not stripped:
        return []
    if any(keyword in stripped for keyword in RISKY_KEYWORDS):
        return [
            _build_review_candidate(
                text=stripped,
                reason="sensitive-or-ambiguous",
            )
        ]
    return []


def is_low_risk_candidate(candidate: Dict[str, Any]) -> bool:
    text = str(candidate.get("content", ""))
    return not any(keyword in text for keyword in RISKY_KEYWORDS)


def should_auto_persist(candidate: Dict[str, Any]) -> bool:
    if candidate.get("is_explicit"):
        return True
    if not is_low_risk_candidate(candidate):
        return False
    tags = {str(tag).strip().lower() for tag in candidate.get("tags") or []}
    if "trait-candidate" in tags:
        return False

    memory_type = candidate.get("memory_type")
    confidence = float(candidate.get("confidence", 0.0))

    if memory_type == "rule" and confidence >= 0.8:
        return True
    if memory_type == "preference" and confidence >= 0.72:
        return True
    if memory_type == "fact" and confidence >= 0.8:
        return True
    return False
