from __future__ import annotations

import unittest


class DomainConstantsTests(unittest.TestCase):
    def test_constants_module_exposes_canonical_values(self) -> None:
        from service import constants

        self.assertEqual("active", constants.STATUS_ACTIVE)
        self.assertEqual("manual", constants.SOURCE_MANUAL)
        self.assertEqual("working_memory", constants.ACTION_WORKING_MEMORY)
        self.assertEqual("segment", constants.SNAPSHOT_SEGMENT)
        self.assertIn(constants.STATUS_ARCHIVED, constants.MEMORY_STATUSES)
        self.assertIn(constants.ACTION_IGNORE, constants.INFERENCE_ACTIONS)
        self.assertIn(constants.SNAPSHOT_GLOBAL_TOPIC, constants.SNAPSHOT_LEVELS)

    def test_schema_defaults_reuse_domain_constants(self) -> None:
        from service import constants
        from service.schemas import ContextSyncRequest, PromoteRequest, UpsertRequest

        self.assertEqual(constants.SOURCE_MANUAL, UpsertRequest(title="t", content="c").source_type)
        self.assertEqual(constants.STATUS_ACTIVE, UpsertRequest(title="t", content="c").status)
        self.assertEqual(constants.SOURCE_CONVERSATION, PromoteRequest(text="hello").source_type)
        self.assertEqual(constants.DEFAULT_SESSION_KEY, ContextSyncRequest().session_key)


if __name__ == "__main__":
    unittest.main()
