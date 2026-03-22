from __future__ import annotations

import unittest


class SchemaModelTests(unittest.TestCase):
    def test_recall_result_coerces_internal_strategy_and_hook_entries(self) -> None:
        from service.schemas import (
            EntityRelationHookEntry,
            FactHintHookEntry,
            InternalStrategy,
            PreferenceHintHookEntry,
            RecallResult,
            RecentTopicHookEntry,
        )

        result = RecallResult(
            query_text="黑咖啡 提神",
            internal_strategy={
                "style": "gentle_personalization",
                "should_recall": True,
                "reasons": ["high-confidence memory"],
                "followup_hooks": ["recent topic: 最近在研究茶饮 -> 最近你在比较乌龙茶和咖啡"],
                "safe_hooks": ["recent topic: 最近在研究茶饮 -> 最近你在比较乌龙茶和咖啡"],
                "internal_only_hooks": ["内部线索：小王（friend_xiaowang）与当前话题相关，关系点是 responsible_for；仅供内部参考。"],
                "hook_entries": [
                    {
                        "kind": "recent_topic",
                        "visibility": "safe",
                        "text": "recent topic: 最近在研究茶饮 -> 最近你在比较乌龙茶和咖啡",
                        "topic": "最近在研究茶饮",
                        "summary": "最近你在比较乌龙茶和咖啡",
                        "use_priority": 40,
                        "confidence_band": "medium",
                    },
                    {
                        "kind": "preference_hint",
                        "visibility": "safe",
                        "text": "记忆提示：你长期喜欢黑咖啡；可直接作为轻量个性化信息融合。",
                        "memory_id": 3,
                        "memory_title": "favorite_drink: 黑咖啡",
                        "attribute_key": "favorite_drink",
                        "integration_hint": "gentle_personalization",
                        "use_priority": 90,
                        "confidence_band": "high",
                    },
                    {
                        "kind": "fact_hint",
                        "visibility": "safe",
                        "text": "记忆提示：你最近在维护 memory MCP 项目；仅在确实相关时再自然带出。",
                        "memory_id": 11,
                        "memory_title": "current_project: memory MCP",
                        "attribute_key": "current_project",
                        "integration_hint": "answer_normally",
                        "use_priority": 60,
                        "confidence_band": "medium",
                    },
                    {
                        "kind": "entity_relation",
                        "visibility": "internal_only",
                        "text": "内部线索：小王（friend_xiaowang）与当前话题相关，关系点是 responsible_for；仅供内部参考。",
                        "subject_key": "friend_xiaowang",
                        "display_name": "小王",
                        "reasons": ["responsible_for"],
                        "integration_hint": "internal_reference_only",
                        "use_priority": 85,
                        "confidence_band": "high",
                    },
                ],
                "recommended_primary_hook": {
                    "kind": "preference_hint",
                    "visibility": "safe",
                    "text": "记忆提示：你长期喜欢黑咖啡；可直接作为轻量个性化信息融合。",
                    "memory_id": 3,
                    "memory_title": "favorite_drink: 黑咖啡",
                    "attribute_key": "favorite_drink",
                    "integration_hint": "gentle_personalization",
                    "use_priority": 90,
                    "confidence_band": "high",
                },
                "recommended_secondary_hooks": [
                    {
                        "kind": "entity_relation",
                        "visibility": "internal_only",
                        "text": "内部线索：小王（friend_xiaowang）与当前话题相关，关系点是 responsible_for；仅供内部参考。",
                        "subject_key": "friend_xiaowang",
                        "display_name": "小王",
                        "reasons": ["responsible_for"],
                        "integration_hint": "internal_reference_only",
                        "use_priority": 85,
                        "confidence_band": "high",
                    },
                    {
                        "kind": "fact_hint",
                        "visibility": "safe",
                        "text": "记忆提示：你最近在维护 memory MCP 项目；仅在确实相关时再自然带出。",
                        "memory_id": 11,
                        "memory_title": "current_project: memory MCP",
                        "attribute_key": "current_project",
                        "integration_hint": "answer_normally",
                        "use_priority": 60,
                        "confidence_band": "medium",
                    },
                ],
                "disclosure_warnings": ["朋友小王高血压: internal_only"],
            },
        )

        self.assertIsInstance(result.internal_strategy, InternalStrategy)
        self.assertEqual("gentle_personalization", result.internal_strategy.style)
        self.assertEqual(4, len(result.internal_strategy.hook_entries))
        self.assertIsInstance(result.internal_strategy.hook_entries[0], RecentTopicHookEntry)
        self.assertEqual("recent_topic", result.internal_strategy.hook_entries[0].kind)
        self.assertEqual("最近在研究茶饮", result.internal_strategy.hook_entries[0].topic)
        self.assertEqual(40, result.internal_strategy.hook_entries[0].use_priority)
        self.assertEqual("medium", result.internal_strategy.hook_entries[0].confidence_band)
        self.assertIsInstance(result.internal_strategy.hook_entries[1], PreferenceHintHookEntry)
        self.assertEqual(3, result.internal_strategy.hook_entries[1].memory_id)
        self.assertEqual("favorite_drink", result.internal_strategy.hook_entries[1].attribute_key)
        self.assertEqual(90, result.internal_strategy.hook_entries[1].use_priority)
        self.assertEqual("high", result.internal_strategy.hook_entries[1].confidence_band)
        self.assertIsInstance(result.internal_strategy.hook_entries[2], FactHintHookEntry)
        self.assertEqual(11, result.internal_strategy.hook_entries[2].memory_id)
        self.assertEqual("current_project", result.internal_strategy.hook_entries[2].attribute_key)
        self.assertEqual(60, result.internal_strategy.hook_entries[2].use_priority)
        self.assertEqual("medium", result.internal_strategy.hook_entries[2].confidence_band)
        self.assertIsInstance(result.internal_strategy.hook_entries[3], EntityRelationHookEntry)
        self.assertEqual("friend_xiaowang", result.internal_strategy.hook_entries[3].subject_key)
        self.assertEqual(85, result.internal_strategy.hook_entries[3].use_priority)
        self.assertEqual("high", result.internal_strategy.hook_entries[3].confidence_band)
        self.assertIsInstance(result.internal_strategy.recommended_primary_hook, PreferenceHintHookEntry)
        self.assertEqual("preference_hint", result.internal_strategy.recommended_primary_hook.kind)
        self.assertEqual(90, result.internal_strategy.recommended_primary_hook.use_priority)
        self.assertEqual(2, len(result.internal_strategy.recommended_secondary_hooks))
        self.assertIsInstance(result.internal_strategy.recommended_secondary_hooks[0], EntityRelationHookEntry)
        self.assertIsInstance(result.internal_strategy.recommended_secondary_hooks[1], FactHintHookEntry)


if __name__ == "__main__":
    unittest.main()
