from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch


class MemoryMaintenanceScriptTests(unittest.TestCase):
    @patch("scripts.memory_maintenance.maintain_memory_store")
    def test_main_outputs_json_summary(self, maintain_memory_store_mock) -> None:
        from scripts import memory_maintenance

        maintain_memory_store_mock.return_value = {
            "scanned_count": 12,
            "updated_count": 3,
            "dry_run": True,
            "changed_ids": [1, 2, 4],
            "lifecycle_counts": {"cold": 2, "stale": 1},
            "updated_memories": [{"id": 1}, {"id": 2}, {"id": 4}],
        }

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = memory_maintenance.main(
                ["--limit", "20", "--dry-run", "--include-archived", "--user-code", "LYB"]
            )

        maintain_memory_store_mock.assert_called_once_with(
            user_code="LYB",
            limit=20,
            dry_run=True,
            include_archived=True,
        )
        self.assertEqual(0, exit_code)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(3, payload["data"]["updated_count"])


if __name__ == "__main__":
    unittest.main()
