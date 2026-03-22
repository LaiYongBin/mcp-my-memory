from __future__ import annotations

import unittest


class EntityGraphTests(unittest.TestCase):
    def test_infer_edge_relation_type_uses_responsibility_signal_when_present(self) -> None:
        from service.entity_graph import infer_edge_relation_type

        self.assertEqual(
            "responsible_for",
            infer_edge_relation_type(
                {
                    "subject_key": "friend_xiaowang",
                    "related_subject_key": "project_memory_mcp",
                    "category": "relationship",
                    "value_text": "负责后端",
                    "claim": "小王在 memory mcp 项目里负责后端",
                }
            ),
        )

    def test_infer_edge_relation_type_detects_collaboration_signal(self) -> None:
        from service.entity_graph import infer_edge_relation_type

        self.assertEqual(
            "collaborates_with",
            infer_edge_relation_type(
                {
                    "subject_key": "friend_xiaowang",
                    "related_subject_key": "team_platform",
                    "category": "relationship",
                    "value_text": "一起维护服务",
                    "claim": "小王和平台团队一起维护这个服务",
                }
            ),
        )

    def test_infer_display_name_prefers_captured_chinese_name(self) -> None:
        from service.entity_graph import infer_display_name

        display_name = infer_display_name(
            "friend_xiaowang",
            [
                {
                    "title": "friend-health-20260322162430",
                    "content": "你的朋友小王有高血压，最近在控制饮食。",
                    "value_text": "朋友小王有高血压",
                }
            ],
        )

        self.assertEqual("小王", display_name)

    def test_infer_relation_type_from_subject_key_prefix(self) -> None:
        from service.entity_graph import infer_relation_type

        self.assertEqual("friend", infer_relation_type("friend_xiaowang"))
        self.assertEqual("partner", infer_relation_type("partner_lin"))
        self.assertEqual("project", infer_relation_type("project_memory_mcp"))
        self.assertEqual("entity", infer_relation_type("misc_topic"))


if __name__ == "__main__":
    unittest.main()
