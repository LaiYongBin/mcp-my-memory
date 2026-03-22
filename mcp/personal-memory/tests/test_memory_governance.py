from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class MemoryGovernanceTests(unittest.TestCase):
    def test_third_party_health_memory_is_restricted(self) -> None:
        from service.memory_governance import derive_memory_governance

        governance = derive_memory_governance(
            {
                "title": "朋友小王高血压",
                "content": "你的朋友小王有高血压",
                "subject_key": "friend_xiaowang",
                "attribute_key": "health_condition",
                "tags": ["health", "friend"],
            }
        )

        self.assertEqual("restricted", governance["sensitivity_level"])
        self.assertEqual("internal_only", governance["disclosure_policy"])

    def test_explicit_high_confidence_memory_becomes_stable_after_recall(self) -> None:
        from service.memory_governance import derive_lifecycle_state

        lifecycle = derive_lifecycle_state(
            {
                "confidence": 0.95,
                "is_explicit": True,
                "recall_count": 2,
                "status": "active",
                "updated_at": datetime.now(timezone.utc),
                "valid_to": None,
                "conflict_with_id": None,
            }
        )

        self.assertEqual("stable", lifecycle)

    def test_old_unrecalled_context_memory_becomes_cold(self) -> None:
        from service.memory_governance import derive_lifecycle_state

        lifecycle = derive_lifecycle_state(
            {
                "memory_type": "context",
                "confidence": 0.55,
                "is_explicit": False,
                "recall_count": 0,
                "status": "active",
                "updated_at": datetime.now(timezone.utc) - timedelta(days=45),
                "valid_to": None,
                "conflict_with_id": None,
            }
        )

        self.assertEqual("cold", lifecycle)

    def test_eval_fixtures_cover_governance_and_lifecycle_expectations(self) -> None:
        from service.memory_governance import derive_lifecycle_state, derive_memory_governance

        cases = json.loads((FIXTURES_DIR / "memory_governance_eval_cases.json").read_text(encoding="utf-8"))

        for case in cases:
            memory = dict(case["memory"])
            if "updated_at_days_ago" in memory:
                memory["updated_at"] = datetime.now(timezone.utc) - timedelta(days=int(memory.pop("updated_at_days_ago")))
            else:
                memory.setdefault("updated_at", datetime.now(timezone.utc))
            memory.setdefault("status", "active")
            memory.setdefault("valid_to", None)
            memory.setdefault("conflict_with_id", None)
            governance = derive_memory_governance(memory)
            lifecycle = derive_lifecycle_state(memory)
            expected = case["expected"]
            if "sensitivity_level" in expected:
                self.assertEqual(expected["sensitivity_level"], governance["sensitivity_level"], case["name"])
            if "disclosure_policy" in expected:
                self.assertEqual(expected["disclosure_policy"], governance["disclosure_policy"], case["name"])
            if "lifecycle_state" in expected:
                self.assertEqual(expected["lifecycle_state"], lifecycle, case["name"])


if __name__ == "__main__":
    unittest.main()
