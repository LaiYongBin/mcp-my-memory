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


class InferEdgeRelationTypeTests(unittest.TestCase):
    def _infer(self, item: dict) -> str:
        from service.entity_graph import infer_edge_relation_type
        return infer_edge_relation_type(item)

    def test_favorite_attribute_returns_associated_preference(self) -> None:
        result = self._infer({"attribute_key": "favorite_drink", "subject_key": "user"})
        self.assertEqual("associated_preference", result)

    def test_preference_attribute_returns_associated_preference(self) -> None:
        result = self._infer({"attribute_key": "preference_style", "subject_key": "user"})
        self.assertEqual("associated_preference", result)

    def test_health_attribute_with_related_subject_returns_responsible_for(self) -> None:
        result = self._infer({
            "attribute_key": "health_care",
            "subject_key": "user",
            "related_subject_key": "friend_a",
        })
        self.assertEqual("responsible_for", result)

    def test_new_keyword_roommate_returns_lives_with(self) -> None:
        result = self._infer({"content": "小王是我的室友", "subject_key": "friend_xiaowang"})
        self.assertEqual("lives_with", result)

    def test_new_keyword_mentor_returns_mentor_of(self) -> None:
        result = self._infer({"content": "他是我的导师", "subject_key": "mentor_zhang"})
        self.assertEqual("mentor_of", result)

    def test_priority_favorite_over_semantic(self) -> None:
        result = self._infer({
            "attribute_key": "favorite_tool",
            "content": "一起合作",
            "subject_key": "user",
        })
        self.assertEqual("associated_preference", result)


class TwoHopConnectionTests(unittest.TestCase):
    def test_empty_input_returns_empty(self) -> None:
        from service.entity_graph import find_two_hop_connections
        result = find_two_hop_connections(source_subject_keys=[], user_code="LYB")
        self.assertEqual([], result)

    def test_two_hop_excludes_user_always(self) -> None:
        """'user' 始终在 exclude 列表中，即使调用者未传入。"""
        from unittest.mock import patch, MagicMock
        from service.entity_graph import find_two_hop_connections

        with patch("service.entity_graph.get_conn") as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor

            find_two_hop_connections(
                source_subject_keys=["friend_a"],
                exclude_subject_keys=None,
                user_code="LYB",
            )
            call_args = mock_cursor.execute.call_args
            params = call_args[0][1]
            exclude_list = params[1]
            self.assertIn("user", exclude_list)

    def test_returns_correct_fields(self) -> None:
        from unittest.mock import patch, MagicMock
        from service.entity_graph import find_two_hop_connections

        with patch("service.entity_graph.get_conn") as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = [
                {"via_entity": "friend_a", "target_subject_key": "project_x", "relation_type": "participates_in"}
            ]
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor

            result = find_two_hop_connections(
                source_subject_keys=["friend_a"],
                user_code="LYB",
            )
            self.assertEqual(1, len(result))
            self.assertEqual("friend_a", result[0]["via_entity"])


if __name__ == "__main__":
    unittest.main()
