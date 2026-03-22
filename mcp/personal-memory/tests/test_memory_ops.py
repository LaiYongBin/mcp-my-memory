"""Tests for memory_ops module."""
from __future__ import annotations

import unittest


class MaintainMemoryStoreFilterTests(unittest.TestCase):
    def test_maintain_accepts_lifecycle_states_param(self) -> None:
        """maintain_memory_store 应接受 lifecycle_states 参数。"""
        import inspect
        from service.memory_ops import maintain_memory_store
        sig = inspect.signature(maintain_memory_store)
        self.assertIn("lifecycle_states", sig.parameters)
        self.assertIn("memory_types", sig.parameters)
        self.assertIn("categories", sig.parameters)

    def test_maintenance_result_has_filter_applied(self) -> None:
        from service.schemas import MaintenanceResult
        result = MaintenanceResult(
            scanned_count=0,
            updated_count=0,
            dry_run=True,
            changed_ids=[],
            lifecycle_counts={},
            updated_memories=[],
            filter_applied={"lifecycle_states": ["cold"]},
        )
        self.assertEqual({"lifecycle_states": ["cold"]}, result.filter_applied)


class HybridSearchFallbackTests(unittest.TestCase):
    def test_hybrid_search_enabled_constant_is_bool(self) -> None:
        from service.constants import HYBRID_SEARCH_ENABLED
        self.assertIsInstance(HYBRID_SEARCH_ENABLED, bool)

    def test_hybrid_search_disabled_by_default(self) -> None:
        import os
        os.environ.pop("LYB_SKILL_MEMORY_DB_HYBRID_SEARCH", None)
        import importlib
        import service.constants
        importlib.reload(service.constants)
        from service.constants import HYBRID_SEARCH_ENABLED
        self.assertFalse(HYBRID_SEARCH_ENABLED)


class MergeDuplicateMemoriesTests(unittest.TestCase):
    def test_merge_result_schema_exists(self) -> None:
        from service.schemas import MergeResult
        result = MergeResult(merged_pairs=[], merged_count=0, dry_run=True)
        self.assertTrue(result.dry_run)
        self.assertEqual(0, result.merged_count)

    def test_dry_run_does_not_write_db(self) -> None:
        from unittest.mock import patch, MagicMock
        from service.memory_ops import merge_duplicate_memories

        with patch("service.memory_ops.get_conn") as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = [
                {"master_candidate_id": 1, "slave_candidate_id": 2, "distance": 0.05}
            ]
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
            mock_conn.return_value.__enter__.return_value.commit.return_value = None

            with patch("service.memory_ops.get_memory") as mock_get:
                mock_get.side_effect = lambda mid, uc: {
                    "id": mid, "confidence": 0.8, "updated_at": "2026-01-01",
                    "content": f"内容{mid}", "tags": [], "status": "active"
                }
                result = merge_duplicate_memories(
                    user_code="LYB",
                    similarity_threshold=0.92,
                    dry_run=True,
                    limit=10,
                )
            mock_conn.return_value.__enter__.return_value.commit.assert_not_called()


class StaleMemoryChallengeTests(unittest.TestCase):
    def test_suggested_question_favorite(self) -> None:
        from service.memory_ops import _suggested_challenge_question
        q = _suggested_challenge_question({"attribute_key": "favorite_drink", "value_text": "黑咖啡"})
        self.assertIn("黑咖啡", q)
        self.assertIn("喜欢", q)

    def test_suggested_question_dislike(self) -> None:
        from service.memory_ops import _suggested_challenge_question
        q = _suggested_challenge_question({"attribute_key": "dislike_food", "value_text": "香菜"})
        self.assertIn("香菜", q)
        self.assertIn("不喜欢", q)

    def test_suggested_question_current_goal(self) -> None:
        from service.memory_ops import _suggested_challenge_question
        q = _suggested_challenge_question({"attribute_key": "current_goal", "value_text": "减肥", "title": "减肥"})
        self.assertIn("减肥", q)

    def test_suggested_question_generic(self) -> None:
        from service.memory_ops import _suggested_challenge_question
        q = _suggested_challenge_question({"attribute_key": "other", "title": "某个记忆"})
        self.assertIn("某个记忆", q)


if __name__ == "__main__":
    unittest.main()
