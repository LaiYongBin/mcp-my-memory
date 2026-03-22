from __future__ import annotations

import unittest


class EntityMemoryTests(unittest.TestCase):
    def test_summarize_entities_from_memories_groups_subject_keys(self) -> None:
        from service.entity_memory import summarize_entities_from_memories

        entities = summarize_entities_from_memories(
            [
                {
                    "subject_key": "friend_xiaowang",
                    "attribute_key": "health_condition",
                    "category": "relationship",
                    "title": "朋友小王高血压",
                    "sensitivity_level": "restricted",
                    "disclosure_policy": "internal_only",
                    "updated_at": "2026-03-22T00:00:00+00:00",
                },
                {
                    "subject_key": "friend_xiaowang",
                    "attribute_key": "relationship_fact",
                    "category": "relationship",
                    "title": "小王是你的朋友",
                    "sensitivity_level": "sensitive",
                    "disclosure_policy": "user_confirm",
                    "updated_at": "2026-03-21T00:00:00+00:00",
                },
            ]
        )

        self.assertEqual(1, len(entities))
        self.assertEqual("friend_xiaowang", entities[0]["subject_key"])
        self.assertEqual("friend", entities[0]["relation_type"])
        self.assertEqual(2, entities[0]["memory_count"])
        self.assertEqual("restricted", entities[0]["sensitivity_level"])
        self.assertEqual("internal_only", entities[0]["disclosure_policy"])


if __name__ == "__main__":
    unittest.main()
