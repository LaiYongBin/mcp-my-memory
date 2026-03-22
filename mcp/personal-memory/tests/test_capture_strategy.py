from __future__ import annotations

import unittest
from unittest.mock import patch


class ExtractionStrategyTests(unittest.TestCase):
    def test_explicit_remember_command_can_auto_persist(self) -> None:
        from service.extraction import extract_candidates, should_auto_persist

        candidates = extract_candidates("记住我最喜欢黑咖啡")

        self.assertEqual(1, len(candidates))
        candidate = candidates[0]
        self.assertTrue(should_auto_persist(candidate))
        self.assertTrue(candidate["is_explicit"])

    def test_non_explicit_self_description_does_not_use_heuristic_capture(self) -> None:
        from service.extraction import extract_candidates, should_auto_persist

        candidates = extract_candidates("我是一个很感性的人")

        self.assertEqual([], candidates)

    def test_non_explicit_trait_statement_does_not_use_heuristic_capture(self) -> None:
        from service.extraction import extract_candidates

        candidates = extract_candidates("我很感性")

        self.assertEqual([], candidates)


class AnalyzerFallbackStrategyTests(unittest.TestCase):
    def test_analysis_prompt_mentions_related_subject_guidance(self) -> None:
        from service.analyzer import _analysis_prompt

        prompt = _analysis_prompt(
            user_text="我的朋友小王在 memory mcp 项目里负责后端。",
            assistant_text="这说明小王和项目之间有明确关系。",
            recent_memories=[],
        )

        self.assertIn("related_subject", prompt)
        self.assertIn("双实体", prompt)
        self.assertIn("我的朋友小王在 memory mcp 项目里负责后端", prompt)

    def test_build_analysis_item_preserves_related_subject(self) -> None:
        from service.analyzer import build_analysis_item

        item = build_analysis_item(
            category="relationship",
            subject="friend_xiaowang",
            related_subject="project_memory_mcp",
            attribute="relationship_fact",
            value="负责后端",
            claim="小王在 memory mcp 项目里负责后端",
            rationale="明确描述了实体之间的关系",
            evidence_type="observed",
            time_scope="mid_term",
            action="long_term",
            confidence=0.7,
        )

        self.assertEqual("project_memory_mcp", item["related_subject"])

    @patch("service.analyzer.get_settings", return_value={"memory_user": "LYB"})
    @patch("service.analyzer.analyzer_enabled", return_value=False)
    def test_identity_self_description_stays_conservative_without_analyzer(
        self, _analyzer_enabled_mock, _get_settings_mock
    ) -> None:
        from service.analyzer import analyze_turn

        items = analyze_turn(user_text="我是一个很感性的人")

        self.assertEqual(1, len(items))
        item = items[0]
        self.assertEqual("ephemeral", item["attribute"])
        self.assertEqual("ignore", item["action"])
        self.assertIn("conservative-fallback", item["tags"])

    @patch("service.analyzer.get_settings", return_value={"memory_user": "LYB"})
    @patch("service.analyzer.analyzer_enabled", return_value=False)
    def test_simple_trait_statement_stays_conservative_without_analyzer(
        self, _analyzer_enabled_mock, _get_settings_mock
    ) -> None:
        from service.analyzer import analyze_turn

        items = analyze_turn(user_text="我很感性")

        self.assertEqual(1, len(items))
        item = items[0]
        self.assertEqual("ephemeral", item["attribute"])
        self.assertEqual("ignore", item["action"])
        self.assertIn("conservative-fallback", item["tags"])

    @patch("service.analyzer.get_settings", return_value={"memory_user": "LYB"})
    @patch("service.analyzer.analyzer_enabled", return_value=False)
    def test_short_term_focus_prefers_working_memory(
        self, _analyzer_enabled_mock, _get_settings_mock
    ) -> None:
        from service.analyzer import analyze_turn

        items = analyze_turn(user_text="这周先优先排查支付模块的超时问题")

        self.assertEqual(1, len(items))
        item = items[0]
        self.assertEqual("current_focus", item["attribute"])
        self.assertEqual("working_memory", item["action"])

    @patch("service.analyzer.get_settings", return_value={"memory_user": "LYB"})
    @patch("service.analyzer.analyzer_enabled", return_value=False)
    def test_explicit_relationship_statement_extracts_related_subject_conservatively(
        self, _analyzer_enabled_mock, _get_settings_mock
    ) -> None:
        from service.analyzer import analyze_turn

        items = analyze_turn(user_text="我的朋友小王在 memory mcp 项目里负责后端。")

        self.assertEqual(1, len(items))
        item = items[0]
        self.assertEqual("friend_小王", item["subject"])
        self.assertEqual("project_memory_mcp", item["related_subject"])
        self.assertEqual("relationship_fact", item["attribute"])
        self.assertEqual("relationship", item["category"])
        self.assertEqual("long_term", item["action"])
        self.assertIn("entity-link", item["tags"])


class EvidencePromotionTests(unittest.TestCase):
    def _item(self, evidence_type: str, time_scope: str, confidence: float, action: str = "long_term") -> dict:
        return {"action": action, "evidence_type": evidence_type, "time_scope": time_scope, "confidence": confidence}

    def _evidence(self, evidence_type: str, occurrence_count: int = 1, support_score: float = 0.0) -> dict:
        return {"evidence_type": evidence_type, "occurrence_count": occurrence_count, "support_score": support_score}

    def test_explicit_long_term_high_confidence_promotes(self) -> None:
        from service.evidence import evidence_supports_promotion
        self.assertTrue(evidence_supports_promotion(
            self._item("explicit", "long_term", 0.85),
            self._evidence("explicit"),
        ))

    def test_explicit_long_term_below_threshold_does_not_promote(self) -> None:
        from service.evidence import evidence_supports_promotion
        # confidence=0.84 is just below the 0.85 floor — must NOT fast-track promote
        self.assertFalse(evidence_supports_promotion(
            self._item("explicit", "long_term", 0.84),
            self._evidence("explicit"),
        ))

    def test_explicit_enough_occurrence_promotes_regardless_of_confidence(self) -> None:
        from service.evidence import evidence_supports_promotion
        # occurrence_count >= 2 path is independent of the confidence floor
        self.assertTrue(evidence_supports_promotion(
            self._item("explicit", "mid_term", 0.6),
            self._evidence("explicit", occurrence_count=2),
        ))


class WorkingMemoryPromotionTests(unittest.TestCase):
    def test_consolidate_calls_evidence_gate_not_bypass(self) -> None:
        """consolidate_working_memories 必须走 evidence_supports_promotion，不能直接提升。"""
        from unittest.mock import patch, MagicMock
        import service.capture_cycle as cc

        fake_row = {
            "memory_key": "abc123",
            "summary": "这周先优先排查支付模块的超时问题",
            "source_text": "这周先优先排查支付模块的超时问题",
            "importance": 5,
            "id": 99,
        }

        with patch("service.capture_cycle.get_conn") as mock_conn, \
             patch("service.capture_cycle.accumulate_evidence") as mock_acc, \
             patch("service.capture_cycle.evidence_supports_promotion") as mock_sup, \
             patch("service.capture_cycle.upsert_memory") as mock_upsert:

            mock_cursor = MagicMock()
            mock_cursor.fetchall.side_effect = [[], [fake_row]]
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
            mock_conn.return_value.__enter__.return_value.commit.return_value = None

            mock_acc.return_value = {"occurrence_count": 1, "support_score": 0.5}
            mock_sup.return_value = False

            cc.consolidate_working_memories(user_code="LYB")

            mock_acc.assert_called_once()
            mock_upsert.assert_not_called()

    def test_consolidate_promotes_when_evidence_satisfied(self) -> None:
        from unittest.mock import patch, MagicMock
        import service.capture_cycle as cc

        fake_row = {
            "memory_key": "def456",
            "summary": "用户喜欢黑咖啡",
            "source_text": "用户喜欢黑咖啡",
            "importance": 4,
            "id": 100,
        }

        with patch("service.capture_cycle.get_conn") as mock_conn, \
             patch("service.capture_cycle.accumulate_evidence") as mock_acc, \
             patch("service.capture_cycle.evidence_supports_promotion") as mock_sup, \
             patch("service.capture_cycle.promoted_confidence") as mock_conf, \
             patch("service.capture_cycle.upsert_memory") as mock_upsert:

            mock_cursor = MagicMock()
            mock_cursor.fetchall.side_effect = [[], [fake_row]]
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
            mock_conn.return_value.__enter__.return_value.commit.return_value = None

            mock_acc.return_value = {"id": 1, "occurrence_count": 3, "support_score": 2.0}
            mock_sup.return_value = True
            mock_conf.return_value = 0.85

            cc.consolidate_working_memories(user_code="LYB")

            mock_acc.assert_called_once()
            mock_sup.assert_called_once()
            mock_upsert.assert_called_once()


if __name__ == "__main__":
    unittest.main()
