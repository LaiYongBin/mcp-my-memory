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


if __name__ == "__main__":
    unittest.main()
