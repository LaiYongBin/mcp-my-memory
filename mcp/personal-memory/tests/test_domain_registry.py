from __future__ import annotations

import unittest
from unittest.mock import patch


class DomainRegistryResolutionTests(unittest.TestCase):
    @patch("service.domain_registry._create_domain_value")
    @patch("service.domain_registry.lookup_domain_value")
    @patch("service.domain_registry._upsert_domain_alias")
    @patch("service.domain_registry.get_conn")
    def test_approve_domain_candidate_can_override_canonical_and_create_alias(
        self,
        get_conn_mock,
        upsert_alias_mock,
        lookup_domain_value_mock,
        create_domain_value_mock,
    ) -> None:
        from service.domain_registry import approve_domain_candidate

        candidate_row = {
            "id": 3,
            "domain_name": "memory_type",
            "proposed_value_key": "Friend Profile",
            "normalized_value_key": "friend_profile",
            "canonical_value_key": None,
            "source": "analyzer",
            "source_ref": "turn:1",
            "reason": "merge into relationship",
            "confidence": 0.8,
            "status": "pending",
            "created_by": "LYB",
            "metadata": {},
            "created_at": "2026-03-22T00:00:00+00:00",
            "updated_at": "2026-03-22T00:00:00+00:00",
        }
        updated_candidate = candidate_row | {
            "canonical_value_key": "relationship",
            "status": "approved",
        }
        cursor = get_conn_mock.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [candidate_row, updated_candidate]
        lookup_domain_value_mock.return_value = {
            "domain_name": "memory_type",
            "value_key": "relationship",
        }
        upsert_alias_mock.return_value = {
            "domain_name": "memory_type",
            "alias_key": "friend_profile",
            "canonical_value_key": "relationship",
        }

        result = approve_domain_candidate(3, canonical_value_key="relationship")

        self.assertEqual("relationship", result["value"]["value_key"])
        self.assertEqual("approved", result["candidate"]["status"])
        self.assertEqual("relationship", result["candidate"]["canonical_value_key"])
        self.assertEqual("relationship", result["alias"]["canonical_value_key"])
        create_domain_value_mock.assert_not_called()
        upsert_alias_mock.assert_called_once()

    @patch("service.domain_registry.create_domain_candidate")
    @patch("service.domain_registry.lookup_domain_alias")
    @patch("service.domain_registry.lookup_domain_value")
    @patch("service.domain_registry.get_domain_definition")
    def test_resolve_attribute_domain_creates_candidate_and_uses_default(
        self,
        get_domain_definition_mock,
        lookup_domain_value_mock,
        lookup_domain_alias_mock,
        create_domain_candidate_mock,
    ) -> None:
        from service.domain_registry import resolve_taxonomy_value

        get_domain_definition_mock.return_value = {
            "domain_name": "attribute_key",
            "governance_mode": "manual_review",
            "default_value_key": "memory",
        }
        lookup_domain_value_mock.return_value = None
        lookup_domain_alias_mock.return_value = None
        create_domain_candidate_mock.return_value = {"id": 12, "normalized_value_key": "friend_health_issue"}

        resolved = resolve_taxonomy_value(
            "attribute_key",
            "friend_health_issue",
            source="analyzer",
            reason="new inferred slot",
        )

        self.assertEqual("memory", resolved["value_key"])
        self.assertEqual("candidate", resolved["resolution"])
        self.assertEqual(12, resolved["candidate"]["id"])

    @patch("service.domain_registry.create_domain_candidate")
    @patch("service.domain_registry.lookup_domain_alias")
    @patch("service.domain_registry.lookup_domain_value")
    @patch("service.domain_registry.get_domain_definition")
    def test_resolve_taxonomy_value_maps_alias_to_canonical(
        self,
        get_domain_definition_mock,
        lookup_domain_value_mock,
        lookup_domain_alias_mock,
        create_domain_candidate_mock,
    ) -> None:
        from service.domain_registry import resolve_taxonomy_value

        get_domain_definition_mock.return_value = {
            "domain_name": "source_type",
            "governance_mode": "manual_review",
            "default_value_key": "manual",
        }
        lookup_domain_value_mock.side_effect = [None, {"value_key": "review-approved"}]
        lookup_domain_alias_mock.return_value = {
            "canonical_value_key": "review-approved",
        }

        resolved = resolve_taxonomy_value(
            "source_type",
            "review approved",
            source="test",
        )

        self.assertEqual("review-approved", resolved["value_key"])
        self.assertEqual("alias", resolved["resolution"])
        self.assertFalse(resolved["used_fallback"])
        create_domain_candidate_mock.assert_not_called()

    @patch("service.domain_registry.create_domain_candidate")
    @patch("service.domain_registry.lookup_domain_alias")
    @patch("service.domain_registry.lookup_domain_value")
    @patch("service.domain_registry.get_domain_definition")
    def test_resolve_taxonomy_value_creates_candidate_and_falls_back_for_manual_review(
        self,
        get_domain_definition_mock,
        lookup_domain_value_mock,
        lookup_domain_alias_mock,
        create_domain_candidate_mock,
    ) -> None:
        from service.domain_registry import resolve_taxonomy_value

        get_domain_definition_mock.return_value = {
            "domain_name": "memory_type",
            "governance_mode": "manual_review",
            "default_value_key": "fact",
        }
        lookup_domain_value_mock.return_value = None
        lookup_domain_alias_mock.return_value = None
        create_domain_candidate_mock.return_value = {"id": 8, "normalized_value_key": "friend_profile"}

        resolved = resolve_taxonomy_value(
            "memory_type",
            "Friend Profile",
            source="analyzer",
            source_ref="turn:123",
            reason="analyzer proposed new taxonomy",
        )

        self.assertEqual("fact", resolved["value_key"])
        self.assertEqual("candidate", resolved["resolution"])
        self.assertTrue(resolved["used_fallback"])
        self.assertEqual(8, resolved["candidate"]["id"])
        create_domain_candidate_mock.assert_called_once()

    @patch("service.domain_registry.lookup_domain_alias")
    @patch("service.domain_registry.lookup_domain_value")
    @patch("service.domain_registry.get_domain_definition")
    def test_resolve_taxonomy_value_rejects_unknown_fixed_domain(
        self,
        get_domain_definition_mock,
        lookup_domain_value_mock,
        lookup_domain_alias_mock,
    ) -> None:
        from service.domain_registry import resolve_taxonomy_value

        get_domain_definition_mock.return_value = {
            "domain_name": "action",
            "governance_mode": "fixed",
            "default_value_key": None,
        }
        lookup_domain_value_mock.return_value = None
        lookup_domain_alias_mock.return_value = None

        with self.assertRaises(ValueError):
            resolve_taxonomy_value("action", "defer_to_future", source="test")


if __name__ == "__main__":
    unittest.main()
