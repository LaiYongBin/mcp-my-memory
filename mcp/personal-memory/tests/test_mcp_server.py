from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch


class MCPPersonalMemoryServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        from service import mcp_server

        self.mcp_server = mcp_server
        self.server = mcp_server.create_server()

    async def test_registers_expected_tools(self) -> None:
        tools = await self.server.list_tools()
        names = {tool.name for tool in tools}
        self.assertEqual(
            {
                "search_memories",
                "search_memory_window",
                "add_memory",
                "delete_memory",
                "capture_turn",
                "add_context",
                "search_context",
                "search_recent_dialogue_summaries",
                "search_entities",
                "search_entity_relationships",
                "maintain_entity_graph",
                "recall_for_response",
                "list_domain_values",
                "search_domain_candidates",
                "approve_domain_candidate",
                "reject_domain_candidate",
                "merge_domain_alias",
                "maintain_memory_store",
                "orchestrate_turn_memory",
                "merge_duplicate_memories",
                "get_stale_memories_for_challenge",
            },
            names,
        )

    @patch("service.mcp_server.list_domain_values")
    async def test_list_domain_values_tool_delegates_to_registry(self, list_domain_values_mock) -> None:
        list_domain_values_mock.return_value = [
            {"domain_name": "memory_type", "value_key": "fact"},
            {"domain_name": "memory_type", "value_key": "preference"},
        ]

        _, structured = await self.server.call_tool(
            "list_domain_values",
            {
                "domain_name": "memory_type",
            },
        )

        list_domain_values_mock.assert_called_once_with("memory_type", include_archived=False)
        self.assertEqual(2, structured["count"])
        self.assertEqual("fact", structured["items"][0]["value_key"])

    @patch("service.mcp_server.approve_domain_candidate")
    async def test_approve_domain_candidate_tool_delegates_to_registry(
        self, approve_domain_candidate_mock
    ) -> None:
        approve_domain_candidate_mock.return_value = {
            "candidate": {"id": 4, "status": "approved"},
            "value": {"domain_name": "memory_type", "value_key": "friend_profile"},
        }

        _, structured = await self.server.call_tool(
            "approve_domain_candidate",
            {
                "candidate_id": 4,
            },
        )

        approve_domain_candidate_mock.assert_called_once_with(4)
        self.assertTrue(structured["ok"])
        self.assertEqual("friend_profile", structured["value"]["value_key"])

    @patch("service.mcp_server.approve_domain_candidate")
    async def test_approve_domain_candidate_tool_accepts_canonical_override(
        self, approve_domain_candidate_mock
    ) -> None:
        approve_domain_candidate_mock.return_value = {
            "candidate": {"id": 4, "status": "approved", "canonical_value_key": "relationship"},
            "value": {"domain_name": "memory_type", "value_key": "relationship"},
        }

        _, structured = await self.server.call_tool(
            "approve_domain_candidate",
            {
                "candidate_id": 4,
                "canonical_value_key": "relationship",
            },
        )

        approve_domain_candidate_mock.assert_called_once_with(4, canonical_value_key="relationship")
        self.assertEqual("relationship", structured["value"]["value_key"])

    @patch("service.mcp_server.reject_domain_candidate")
    async def test_reject_domain_candidate_tool_delegates_to_registry(
        self, reject_domain_candidate_mock
    ) -> None:
        reject_domain_candidate_mock.return_value = {
            "candidate": {"id": 7, "status": "rejected"},
            "value": None,
        }

        _, structured = await self.server.call_tool(
            "reject_domain_candidate",
            {
                "candidate_id": 7,
                "reason": "taxonomy too noisy",
            },
        )

        reject_domain_candidate_mock.assert_called_once_with(7, reason="taxonomy too noisy")
        self.assertTrue(structured["ok"])
        self.assertEqual("rejected", structured["candidate"]["status"])

    @patch("service.mcp_server.merge_domain_alias")
    async def test_merge_domain_alias_tool_delegates_to_registry(self, merge_domain_alias_mock) -> None:
        merge_domain_alias_mock.return_value = {
            "alias": {
                "domain_name": "memory_type",
                "alias_key": "friend_profile",
                "canonical_value_key": "relationship",
            },
            "candidate": {"id": 9, "status": "approved"},
            "value": {"domain_name": "memory_type", "value_key": "relationship"},
        }

        _, structured = await self.server.call_tool(
            "merge_domain_alias",
            {
                "domain_name": "memory_type",
                "alias_key": "Friend Profile",
                "canonical_value_key": "relationship",
                "candidate_id": 9,
            },
        )

        merge_domain_alias_mock.assert_called_once_with(
            domain_name="memory_type",
            alias_key="Friend Profile",
            canonical_value_key="relationship",
            candidate_id=9,
        )
        self.assertTrue(structured["ok"])
        self.assertEqual("relationship", structured["alias"]["canonical_value_key"])

    @patch("service.mcp_server.sync_session_context")
    @patch("service.mcp_server.run_capture_cycle")
    async def test_capture_turn_records_turn_and_updates_context(
        self, run_capture_cycle_mock, sync_session_context_mock
    ) -> None:
        run_capture_cycle_mock.return_value = {
            "event_count": 2,
            "analysis_result_count": 1,
            "persisted_count": 1,
        }
        sync_session_context_mock.return_value = {
            "event_count": 2,
            "segment_snapshot": {"id": 22, "topic": "饮食偏好"},
            "topic_snapshot": {"id": 23, "topic": "饮食偏好"},
            "global_topic_snapshot": {"id": 24, "topic": "饮食偏好"},
            "memory_sync": None,
        }

        _, structured = await self.server.call_tool(
            "capture_turn",
            {
                "user_text": "记住我最近开始每天骑车通勤。",
                "assistant_text": "我记下来了，后面可以结合这个习惯来建议。",
                "session_key": "life-2026-03",
                "topic_hint": "通勤和运动",
            },
        )

        run_capture_cycle_mock.assert_called_once_with(
            user_text="记住我最近开始每天骑车通勤。",
            assistant_text="我记下来了，后面可以结合这个习惯来建议。",
            user_code=None,
            session_key="life-2026-03",
            source_ref=None,
            consolidate=True,
        )
        sync_session_context_mock.assert_called_once_with(
            session_key="life-2026-03",
            turns=None,
            user_code=None,
            topic_hint="通勤和运动",
            source_ref=None,
            extract_memory=False,
        )
        self.assertTrue(structured["ok"])
        self.assertEqual(1, structured["capture"]["persisted_count"])
        self.assertEqual(22, structured["context"]["segment_snapshot"]["id"])

    @patch("service.mcp_server.search_entities")
    async def test_search_entities_tool_delegates_to_entity_summary(self, search_entities_mock) -> None:
        search_entities_mock.return_value = [
            {
                "subject_key": "friend_xiaowang",
                "display_name": "xiaowang",
                "relation_type": "friend",
                "memory_count": 2,
            }
        ]

        _, structured = await self.server.call_tool(
            "search_entities",
            {
                "query": "小王",
                "limit": 5,
            },
        )

        search_entities_mock.assert_called_once_with(
            query="小王",
            user_code=None,
            subject_key=None,
            include_archived=False,
            limit=5,
        )
        self.assertEqual(1, structured["count"])
        self.assertEqual("friend_xiaowang", structured["items"][0]["subject_key"])

    @patch("service.mcp_server.search_entity_relationships")
    async def test_search_entity_relationships_tool_delegates_to_graph(
        self, search_entity_relationships_mock
    ) -> None:
        search_entity_relationships_mock.return_value = [
            {
                "source_subject_key": "user",
                "target_subject_key": "friend_xiaowang",
                "relation_type": "friend",
                "evidence_count": 2,
            }
        ]

        _, structured = await self.server.call_tool(
            "search_entity_relationships",
            {
                "query": "小王",
                "limit": 5,
            },
        )

        search_entity_relationships_mock.assert_called_once_with(
            query="小王",
            user_code=None,
            subject_key=None,
            include_archived=False,
            limit=5,
        )
        self.assertEqual(1, structured["count"])
        self.assertEqual("friend_xiaowang", structured["items"][0]["target_subject_key"])

    @patch("service.mcp_server.rebuild_entity_graph")
    async def test_maintain_entity_graph_tool_delegates_to_rebuild(self, rebuild_entity_graph_mock) -> None:
        rebuild_entity_graph_mock.return_value = {
            "profile_count": 2,
            "edge_count": 1,
            "subject_keys": ["user", "friend_xiaowang"],
        }

        _, structured = await self.server.call_tool(
            "maintain_entity_graph",
            {
                "user_code": "LYB",
            },
        )

        rebuild_entity_graph_mock.assert_called_once_with(user_code="LYB")
        self.assertEqual(2, structured["count"])
        self.assertEqual("user", structured["items"][0]["subject_key"])

    @patch("service.mcp_server.search_recent_context_summaries")
    async def test_search_recent_dialogue_summaries_uses_time_window(self, recent_search_mock) -> None:
        recent_search_mock.return_value = [
            {"id": 31, "topic": "最近在看中医", "summary": "你最近在看一些调理血压的资料。"}
        ]

        _, structured = await self.server.call_tool(
            "search_recent_dialogue_summaries",
            {
                "recent_hours": 72,
                "snapshot_levels": ["segment", "topic"],
                "limit": 5,
            },
        )

        recent_search_mock.assert_called_once_with(
            user_code=None,
            session_key=None,
            query="",
            snapshot_levels=["segment", "topic"],
            recent_hours=72,
            limit=5,
        )
        self.assertEqual(1, structured["count"])
        self.assertEqual("最近在看中医", structured["items"][0]["topic"])

    @patch("service.mcp_server.upsert_memory")
    async def test_add_memory_tool_delegates_to_storage(self, upsert_memory_mock) -> None:
        upsert_memory_mock.return_value = {"id": 11, "title": "喜欢黑咖啡", "content": "我喜欢黑咖啡"}

        _, structured = await self.server.call_tool(
            "add_memory",
            {
                "memory_type": "preference",
                "title": "喜欢黑咖啡",
                "content": "我喜欢黑咖啡",
                "tags": ["drink"],
                "importance": 8,
                "is_explicit": True,
            },
        )

        upsert_memory_mock.assert_called_once_with(
            {
                "id": None,
                "user_code": None,
                "memory_type": "preference",
                "title": "喜欢黑咖啡",
                "content": "我喜欢黑咖啡",
                "summary": None,
                "tags": ["drink"],
                "source_type": "manual",
                "source_ref": None,
                "confidence": 0.7,
                "importance": 8,
                "status": "active",
                "is_explicit": True,
                "valid_from": None,
                "valid_to": None,
                "subject_key": None,
                "related_subject_key": None,
                "attribute_key": None,
                "value_text": None,
                "conflict_scope": None,
            }
        )
        self.assertTrue(structured["ok"])
        self.assertEqual(11, structured["memory"]["id"])

    @patch("service.mcp_server.search_memories_by_time_range")
    async def test_search_memory_window_uses_requested_time_field(self, range_search_mock) -> None:
        range_search_mock.return_value = [{"id": 7, "title": "最近提醒"}]

        _, structured = await self.server.call_tool(
            "search_memory_window",
            {
                "time_field": "updated_at",
                "start_at": "2026-03-01T00:00:00",
                "end_at": "2026-03-20T23:59:59",
                "memory_type": "context",
                "limit": 5,
            },
        )

        range_search_mock.assert_called_once_with(
            user_code=None,
            time_field="updated_at",
            start_at="2026-03-01T00:00:00",
            end_at="2026-03-20T23:59:59",
            query="",
            memory_type="context",
            tags=[],
            include_archived=False,
            limit=5,
        )
        self.assertEqual(1, structured["count"])
        self.assertEqual(7, structured["items"][0]["id"])

    @patch("service.mcp_server.search_recent_context_summaries")
    @patch("service.mcp_server.search_context_snapshots")
    @patch("service.mcp_server.search_memories")
    async def test_recall_for_response_merges_memory_and_context_hits(
        self, search_memories_mock, search_context_mock, recent_context_mock
    ) -> None:
        search_memories_mock.return_value = [
            {"id": 3, "title": "朋友小王高血压", "content": "你的朋友小王有高血压", "confidence": 0.92}
        ]
        search_context_mock.return_value = [
            {"id": 5, "topic": "朋友健康近况", "summary": "你提到小王最近在控制血压"}
        ]
        recent_context_mock.return_value = [
            {"id": 8, "topic": "最近在研究食疗", "summary": "你最近也在看通过饮食管理血压的资料。"}
        ]

        _, structured = await self.server.call_tool(
            "recall_for_response",
            {
                "user_message": "芹菜汁有什么作用",
                "draft_response": "芹菜汁可能对血压管理有帮助。",
                "topic_hint": "饮食和健康",
                "memory_limit": 2,
                "context_limit": 2,
                "recent_context_limit": 1,
            },
        )

        search_memories_mock.assert_called_once()
        search_context_mock.assert_called_once()
        recent_context_mock.assert_called_once_with(
            user_code=None,
            session_key=None,
            query="",
            snapshot_levels=["segment", "topic"],
            recent_hours=168,
            limit=1,
        )
        self.assertEqual("芹菜汁有什么作用 饮食和健康 芹菜汁可能对血压管理有帮助。", structured["query_text"])
        self.assertEqual(1, structured["memory_count"])
        self.assertEqual(1, structured["context_count"])
        self.assertEqual(1, structured["recent_context_count"])
        self.assertIn("朋友小王高血压", structured["memory_titles"])
        self.assertIn("最近在研究食疗", structured["recent_context_topics"])
        self.assertIn("最近在研究食疗", structured["suggested_followup_hooks"][0])
        self.assertTrue(structured["should_recall"])
        self.assertEqual("gentle_personalization", structured["suggested_integration_style"])
        self.assertIn("high-confidence memory", structured["decision_reasons"])

    @patch("service.mcp_server.search_context_snapshots")
    @patch("service.mcp_server.search_memories")
    async def test_recall_for_response_can_suppress_weak_irrelevant_hits(
        self, search_memories_mock, search_context_mock
    ) -> None:
        search_memories_mock.return_value = [
            {"id": 9, "title": "检索验证B", "content": "我偏爱美式咖啡这种苦一点的口味。", "confidence": 0.4}
        ]
        search_context_mock.return_value = []

        _, structured = await self.server.call_tool(
            "recall_for_response",
            {
                "user_message": "给我解释一下 TCP 三次握手",
                "draft_response": "TCP 通过 SYN、SYN-ACK、ACK 建立连接。",
                "topic_hint": "网络基础",
                "memory_limit": 2,
                "context_limit": 2,
            },
        )

        self.assertFalse(structured["should_recall"])
        self.assertEqual("answer_normally", structured["suggested_integration_style"])
        self.assertIn("no strong personalization signal", structured["decision_reasons"])

    @patch("service.mcp_server.search_context_snapshots")
    @patch("service.mcp_server.search_memories")
    async def test_recall_for_response_requires_relevance_not_just_personal_memory(
        self, search_memories_mock, search_context_mock
    ) -> None:
        search_memories_mock.return_value = [
            {
                "id": 9,
                "title": "favorite_food: 白菜",
                "content": "白菜",
                "confidence": 0.9,
                "is_explicit": True,
                "vector_score": 0.39,
                "hybrid_score": 0.39,
                "attribute_key": "favorite_food",
            }
        ]
        search_context_mock.return_value = []

        _, structured = await self.server.call_tool(
            "recall_for_response",
            {
                "user_message": "芹菜汁有什么作用",
                "draft_response": "芹菜汁可能对血压管理有帮助。",
                "topic_hint": "饮食和健康",
                "memory_limit": 2,
                "context_limit": 2,
            },
        )

        self.assertFalse(structured["should_recall"])
        self.assertEqual("answer_normally", structured["suggested_integration_style"])
        self.assertIn("no strong personalization signal", structured["decision_reasons"])

    @patch("service.mcp_server.search_recent_context_summaries")
    @patch("service.mcp_server.search_context_snapshots")
    @patch("service.mcp_server.search_memories")
    async def test_recall_for_response_returns_tiered_and_suppressed_memory_groups(
        self, search_memories_mock, search_context_mock, recent_context_mock
    ) -> None:
        search_memories_mock.return_value = [
            {
                "id": 3,
                "title": "favorite_drink: 黑咖啡",
                "content": "我最喜欢黑咖啡",
                "confidence": 0.95,
                "is_explicit": True,
                "hybrid_score": 0.66,
                "attribute_key": "favorite_drink",
                "disclosure_policy": "normal",
                "sensitivity_level": "normal",
                "lifecycle_state": "stable",
            },
            {
                "id": 4,
                "title": "朋友小王高血压",
                "content": "你的朋友小王在饮食管理项目里负责资料整理，也有高血压",
                "confidence": 0.92,
                "is_explicit": True,
                "hybrid_score": 0.71,
                "attribute_key": "health_condition",
                "disclosure_policy": "internal_only",
                "sensitivity_level": "restricted",
                "lifecycle_state": "stable",
                "subject_key": "friend_xiaowang",
                "related_subject_key": "project_diet_plan",
                "value_text": "负责资料整理",
                "claim": "小王在饮食管理项目里负责资料整理",
            },
        ]
        search_context_mock.return_value = [{"id": 6, "topic": "饮食偏好", "summary": "你长期喜欢黑咖啡"}]
        recent_context_mock.return_value = [{"id": 8, "topic": "最近在研究茶饮", "summary": "最近你在比较乌龙茶和咖啡"}]

        _, structured = await self.server.call_tool(
            "recall_for_response",
            {
                "user_message": "黑咖啡提神效果怎么样",
                "draft_response": "黑咖啡通常会有提神作用。",
                "topic_hint": "饮品和习惯",
            },
        )

        self.assertEqual(1, structured["direct_memory_count"])
        self.assertEqual(1, structured["suppressed_memory_count"])
        self.assertEqual("favorite_drink: 黑咖啡", structured["direct_memories"][0]["title"])
        self.assertEqual("朋友小王高血压", structured["suppressed_memories"][0]["title"])
        self.assertIn("internal_only", structured["disclosure_warnings"][0])
        self.assertEqual("stable", structured["direct_memories"][0]["lifecycle_state"])
        self.assertEqual(1, structured["related_entity_count"])
        self.assertEqual("friend_xiaowang", structured["related_entities"][0]["subject_key"])
        self.assertIn("responsible_for", structured["related_entities"][0]["relationship_reasons"])
        self.assertEqual("internal_reference_only", structured["related_entities"][0]["suggested_integration_hint"])
        self.assertTrue(
            any(
                "内部线索" in hook
                and "friend_xiaowang" in hook
                and "responsible_for" in hook
                and "仅供内部参考" in hook
                for hook in structured["suggested_followup_hooks"]
            )
        )
        self.assertIn("gentle_personalization", structured["internal_strategy_summary"])
        self.assertIn("high-confidence memory", structured["internal_strategy_summary"])
        self.assertIn("内部线索", structured["internal_strategy_summary"])
        self.assertEqual("gentle_personalization", structured["internal_strategy"]["style"])
        self.assertIn("high-confidence memory", structured["internal_strategy"]["reasons"])
        self.assertTrue(structured["internal_strategy"]["should_recall"])
        self.assertTrue(structured["internal_strategy"]["followup_hooks"])
        self.assertTrue(structured["internal_strategy"]["hook_entries"])
        self.assertTrue(structured["internal_strategy"]["recommended_primary_hook"])
        self.assertTrue(structured["internal_strategy"]["recommended_secondary_hooks"])
        self.assertTrue(structured["internal_strategy"]["disclosure_warnings"])
        self.assertTrue(structured["internal_strategy"]["safe_hooks"])
        self.assertTrue(structured["internal_strategy"]["internal_only_hooks"])
        self.assertTrue(
            any(
                entry["visibility"] == "safe" and entry["kind"] == "recent_topic"
                for entry in structured["internal_strategy"]["hook_entries"]
            )
        )
        self.assertTrue(
            any(
                entry["visibility"] == "internal_only" and entry["kind"] == "entity_relation"
                for entry in structured["internal_strategy"]["hook_entries"]
            )
        )
        self.assertTrue(
            any(
                entry["visibility"] == "safe" and entry["kind"] == "preference_hint"
                for entry in structured["internal_strategy"]["hook_entries"]
            )
        )
        recent_topic_entry = next(
            entry
            for entry in structured["internal_strategy"]["hook_entries"]
            if entry["visibility"] == "safe" and entry["kind"] == "recent_topic"
        )
        memory_hint_entry = next(
            entry
            for entry in structured["internal_strategy"]["hook_entries"]
            if entry["visibility"] == "safe" and entry["kind"] == "preference_hint"
        )
        entity_relation_entry = next(
            entry
            for entry in structured["internal_strategy"]["hook_entries"]
            if entry["visibility"] == "internal_only" and entry["kind"] == "entity_relation"
        )
        self.assertEqual("最近在研究茶饮", recent_topic_entry["topic"])
        self.assertIn("乌龙茶和咖啡", recent_topic_entry["summary"])
        self.assertEqual(40, recent_topic_entry["use_priority"])
        self.assertEqual("medium", recent_topic_entry["confidence_band"])
        self.assertEqual(3, memory_hint_entry["memory_id"])
        self.assertEqual("favorite_drink: 黑咖啡", memory_hint_entry["memory_title"])
        self.assertEqual("favorite_drink", memory_hint_entry["attribute_key"])
        self.assertEqual("gentle_personalization", memory_hint_entry["integration_hint"])
        self.assertEqual(90, memory_hint_entry["use_priority"])
        self.assertEqual("high", memory_hint_entry["confidence_band"])
        self.assertEqual("friend_xiaowang", entity_relation_entry["subject_key"])
        self.assertIn("responsible_for", entity_relation_entry["reasons"])
        self.assertEqual("internal_reference_only", entity_relation_entry["integration_hint"])
        self.assertEqual(85, entity_relation_entry["use_priority"])
        self.assertEqual("high", entity_relation_entry["confidence_band"])
        self.assertTrue(
            any("recent topic:" in hook for hook in structured["internal_strategy"]["safe_hooks"])
        )
        self.assertTrue(
            any("记忆提示：" in hook for hook in structured["internal_strategy"]["safe_hooks"])
        )
        self.assertTrue(
            any("仅供内部参考" in hook for hook in structured["internal_strategy"]["internal_only_hooks"])
        )
        priorities = [
            entry["use_priority"]
            for entry in structured["internal_strategy"]["hook_entries"]
            if entry.get("use_priority") is not None
        ]
        self.assertEqual(sorted(priorities, reverse=True), priorities)
        kinds_in_order = [entry["kind"] for entry in structured["internal_strategy"]["hook_entries"]]
        self.assertEqual(
            ["preference_hint", "entity_relation", "recent_topic"],
            kinds_in_order[:3],
        )
        self.assertEqual(
            "preference_hint",
            structured["internal_strategy"]["recommended_primary_hook"]["kind"],
        )
        self.assertEqual(
            90,
            structured["internal_strategy"]["recommended_primary_hook"]["use_priority"],
        )
        self.assertEqual(
            "favorite_drink: 黑咖啡",
            structured["internal_strategy"]["recommended_primary_hook"]["memory_title"],
        )
        self.assertEqual(
            ["recent_topic", "entity_relation"],
            [
                hook["kind"]
                for hook in structured["internal_strategy"]["recommended_secondary_hooks"]
            ][:2],
        )

    @patch("service.mcp_server.search_recent_context_summaries")
    @patch("service.mcp_server.search_context_snapshots")
    @patch("service.mcp_server.search_memories")
    async def test_recall_for_response_emits_fact_hint_for_non_preference_memory(
        self, search_memories_mock, search_context_mock, recent_context_mock
    ) -> None:
        search_memories_mock.return_value = [
            {
                "id": 11,
                "title": "current_project: memory MCP",
                "content": "你最近在维护 memory MCP 项目",
                "confidence": 0.88,
                "is_explicit": True,
                "hybrid_score": 0.63,
                "attribute_key": "current_project",
                "disclosure_policy": "normal",
                "sensitivity_level": "normal",
                "lifecycle_state": "stable",
            }
        ]
        search_context_mock.return_value = []
        recent_context_mock.return_value = []

        _, structured = await self.server.call_tool(
            "recall_for_response",
            {
                "user_message": "我们这个记忆系统下一步怎么做",
                "draft_response": "可以先收口召回策略和评测。",
                "topic_hint": "memory MCP 项目规划",
            },
        )

        fact_hint_entry = next(
            entry
            for entry in structured["internal_strategy"]["hook_entries"]
            if entry["visibility"] == "safe" and entry["kind"] == "fact_hint"
        )
        self.assertEqual(11, fact_hint_entry["memory_id"])
        self.assertEqual("current_project: memory MCP", fact_hint_entry["memory_title"])
        self.assertEqual("current_project", fact_hint_entry["attribute_key"])
        self.assertEqual("answer_normally", fact_hint_entry["integration_hint"])
        self.assertEqual(60, fact_hint_entry["use_priority"])
        self.assertEqual("medium", fact_hint_entry["confidence_band"])
        self.assertEqual(
            "fact_hint",
            structured["internal_strategy"]["recommended_primary_hook"]["kind"],
        )
        self.assertEqual([], structured["internal_strategy"]["recommended_secondary_hooks"])
        self.assertTrue(
            any("记忆提示：" in hook for hook in structured["internal_strategy"]["safe_hooks"])
        )

    @patch("service.mcp_server.maintain_memory_store")
    async def test_maintain_memory_store_tool_delegates_to_storage(
        self, maintain_memory_store_mock
    ) -> None:
        maintain_memory_store_mock.return_value = {
            "scanned_count": 5,
            "updated_count": 2,
            "dry_run": False,
            "changed_ids": [4, 7],
            "lifecycle_counts": {"cold": 1, "stale": 1},
            "updated_memories": [{"id": 4}, {"id": 7}],
            "filter_applied": {},
        }

        _, structured = await self.server.call_tool(
            "maintain_memory_store",
            {
                "limit": 50,
                "dry_run": False,
                "include_archived": True,
            },
        )

        maintain_memory_store_mock.assert_called_once_with(
            user_code=None,
            limit=50,
            dry_run=False,
            include_archived=True,
            lifecycle_states=None,
            memory_types=None,
            categories=None,
        )
        self.assertEqual(5, structured["scanned_count"])
        self.assertEqual(2, structured["updated_count"])
        self.assertEqual([4, 7], structured["changed_ids"])

    @patch("service.mcp_server.search_recent_context_summaries")
    @patch("service.mcp_server.search_context_snapshots")
    @patch("service.mcp_server.search_memories")
    async def test_orchestrate_turn_memory_returns_recall_and_capture_plan(
        self, search_memories_mock, search_context_mock, recent_context_mock
    ) -> None:
        search_memories_mock.return_value = [
            {
                "id": 3,
                "title": "favorite_drink: 黑咖啡",
                "content": "我最喜欢黑咖啡",
                "confidence": 0.95,
                "hybrid_score": 0.66,
                "disclosure_policy": "normal",
                "lifecycle_state": "stable",
            }
        ]
        search_context_mock.return_value = [{"id": 6, "topic": "饮食偏好", "summary": "你长期喜欢黑咖啡"}]
        recent_context_mock.return_value = []

        _, structured = await self.server.call_tool(
            "orchestrate_turn_memory",
            {
                "user_message": "黑咖啡提神效果怎么样",
                "draft_response": "黑咖啡通常会有提神作用。",
                "session_key": "coffee",
                "topic_hint": "饮品和习惯",
            },
        )

        self.assertTrue(structured["recall"]["should_recall"])
        self.assertTrue(structured["should_capture"])
        self.assertEqual("coffee", structured["capture_plan"]["session_key"])
        self.assertEqual(
            ["recall_for_response", "answer_user", "capture_turn"],
            structured["recommended_sequence"],
        )
        self.assertIsNone(structured["executed_capture"])

    @patch("service.mcp_server.sync_session_context")
    @patch("service.mcp_server.run_capture_cycle")
    @patch("service.mcp_server.search_recent_context_summaries")
    @patch("service.mcp_server.search_context_snapshots")
    @patch("service.mcp_server.search_memories")
    async def test_orchestrate_turn_memory_can_execute_post_turn_capture(
        self,
        search_memories_mock,
        search_context_mock,
        recent_context_mock,
        run_capture_cycle_mock,
        sync_session_context_mock,
    ) -> None:
        search_memories_mock.return_value = []
        search_context_mock.return_value = []
        recent_context_mock.return_value = []
        run_capture_cycle_mock.return_value = {
            "event_count": 2,
            "analysis_result_count": 1,
            "persisted_count": 1,
        }
        sync_session_context_mock.return_value = {
            "event_count": 2,
            "segment_snapshot": {"id": 21, "topic": "饮食偏好"},
            "topic_snapshot": None,
            "global_topic_snapshot": None,
            "memory_sync": None,
        }

        _, structured = await self.server.call_tool(
            "orchestrate_turn_memory",
            {
                "user_message": "记住我最近开始每天骑车通勤。",
                "assistant_text": "我记下来了，后面可以结合这个习惯来建议。",
                "session_key": "life-2026-03",
                "topic_hint": "通勤和运动",
                "capture_after_response": True,
            },
        )

        run_capture_cycle_mock.assert_called_once_with(
            user_text="记住我最近开始每天骑车通勤。",
            assistant_text="我记下来了，后面可以结合这个习惯来建议。",
            user_code=None,
            session_key="life-2026-03",
            source_ref=None,
            consolidate=True,
        )
        sync_session_context_mock.assert_called_once_with(
            session_key="life-2026-03",
            turns=None,
            user_code=None,
            topic_hint="通勤和运动",
            source_ref=None,
            extract_memory=False,
        )
        self.assertIsNotNone(structured["executed_capture"])
        self.assertEqual(1, structured["executed_capture"]["capture"]["persisted_count"])


class BuildResponsePlanTests(unittest.TestCase):
    def _make_memory(self, title: str, confidence: float = 0.8) -> dict:
        return {
            "id": 1,
            "title": title,
            "content": title,
            "confidence": confidence,
            "is_explicit": False,
            "hybrid_score": 0.0,
            "vector_score": 0.0,
            "rank_score": 0.0,
        }

    def test_answer_normally_when_no_recall(self) -> None:
        from service.mcp_server import _build_response_plan
        plan = _build_response_plan(
            suggested_integration_style="answer_normally",
            direct_memories=[],
            contextual_memories=[],
            suppressed_memories=[],
            safe_hooks=[],
            internal_only_hooks=[],
        )
        self.assertEqual("answer_normally", plan.primary_answer_style)
        self.assertEqual([], plan.inline_memories)
        self.assertEqual("", plan.main_sentence_hint)

    def test_inline_memories_from_direct(self) -> None:
        from service.mcp_server import _build_response_plan
        mem = self._make_memory("用户喜欢黑咖啡", confidence=0.9)
        plan = _build_response_plan(
            suggested_integration_style="direct_personalization",
            direct_memories=[mem],
            contextual_memories=[],
            suppressed_memories=[],
            safe_hooks=[],
            internal_only_hooks=[],
        )
        self.assertEqual("direct_personalization", plan.primary_answer_style)
        self.assertIn("用户喜欢黑咖啡", plan.inline_memories)
        self.assertNotEqual("", plan.main_sentence_hint)

    def test_soft_mentions_from_contextual(self) -> None:
        from service.mcp_server import _build_response_plan
        mem = self._make_memory("用户最近在学骑车", confidence=0.7)
        plan = _build_response_plan(
            suggested_integration_style="gentle_personalization",
            direct_memories=[],
            contextual_memories=[mem],
            suppressed_memories=[],
            safe_hooks=[],
            internal_only_hooks=[],
        )
        self.assertIn("用户最近在学骑车", plan.soft_mentions)
        self.assertEqual([], plan.inline_memories)

    def test_internal_only_from_suppressed_and_hooks(self) -> None:
        from service.mcp_server import _build_response_plan
        mem = self._make_memory("敏感信息", confidence=0.9)
        plan = _build_response_plan(
            suggested_integration_style="gentle_personalization",
            direct_memories=[],
            contextual_memories=[],
            suppressed_memories=[mem],
            safe_hooks=[],
            internal_only_hooks=["内部线索：某某与当前话题相关，仅供内部参考。"],
        )
        self.assertIn("敏感信息", plan.internal_only)
        self.assertEqual(2, len(plan.internal_only))

    def test_followup_hooks_from_safe_hooks(self) -> None:
        from service.mcp_server import _build_response_plan
        plan = _build_response_plan(
            suggested_integration_style="gentle_personalization",
            direct_memories=[],
            contextual_memories=[],
            suppressed_memories=[],
            safe_hooks=["recent topic: 骑车通勤 -> 用户最近每天骑车"],
            internal_only_hooks=[],
        )
        self.assertIn("recent topic: 骑车通勤 -> 用户最近每天骑车", plan.followup_hooks)

    def test_gentle_personalization_with_direct_memories_sets_hint(self) -> None:
        from service.mcp_server import _build_response_plan
        mem = self._make_memory("用户喜欢骑车", confidence=0.75)
        plan = _build_response_plan(
            suggested_integration_style="gentle_personalization",
            direct_memories=[mem],
            contextual_memories=[],
            suppressed_memories=[],
            safe_hooks=[],
            internal_only_hooks=[],
        )
        # gentle_personalization + direct memories → second branch in main_sentence_hint
        self.assertEqual("gentle_personalization", plan.primary_answer_style)
        self.assertIn("用户喜欢骑车", plan.inline_memories)
        self.assertIn("轻量带入", plan.main_sentence_hint)


class PersonalQueryPatternTests(unittest.TestCase):
    def _decide(self, user_message: str) -> dict:
        from service.mcp_server import _decide_recall
        return _decide_recall(
            user_message=user_message,
            draft_response=None,
            topic_hint=None,
            memories=[],
            contexts=[],
        )

    def test_generic_question_with_ni_does_not_trigger_personal_signal(self) -> None:
        result = self._decide("你觉得 Python 和 Go 哪个更好？")
        self.assertFalse(result["should_recall"])
        self.assertNotIn("personalization opportunity in current turn", result["decision_reasons"])

    def test_explicit_reference_triggers_personal_signal(self) -> None:
        from service.mcp_server import _has_pattern, PERSONAL_QUERY_PATTERNS
        self.assertTrue(_has_pattern("之前你说过我喜欢跑步", PERSONAL_QUERY_PATTERNS))

    def test_single_ni_no_longer_in_patterns(self) -> None:
        from service.mcp_server import PERSONAL_QUERY_PATTERNS
        self.assertNotIn("你", PERSONAL_QUERY_PATTERNS)

    def test_phrase_patterns_present(self) -> None:
        from service.mcp_server import PERSONAL_QUERY_PATTERNS
        self.assertIn("之前", PERSONAL_QUERY_PATTERNS)
        self.assertIn("喜欢", PERSONAL_QUERY_PATTERNS)
        self.assertIn("你知道我", PERSONAL_QUERY_PATTERNS)


class EnrichRelatedEntitiesTests(unittest.TestCase):
    def test_low_relevance_entity_memories_are_excluded(self) -> None:
        from service.mcp_server import _enrich_related_entities
        entities = [{"subject_key": "friend_a", "display_name": "小明", "disclosure_policy": "normal"}]
        low_rel_memory = {
            "subject_key": "friend_a",
            "title": "低相关记忆",
            "content": "某些无关内容",
            "hybrid_score": 0.0,
            "vector_score": 0.0,
            "rank_score": 0.0,
        }
        enriched = _enrich_related_entities(entities=entities, memories=[low_rel_memory])
        self.assertEqual([], enriched[0]["relationship_reasons"])

    def test_high_relevance_entity_memory_contributes_reason(self) -> None:
        from service.mcp_server import _enrich_related_entities
        entities = [{"subject_key": "friend_a", "display_name": "小明", "disclosure_policy": "normal"}]
        high_rel_memory = {
            "subject_key": "friend_a",
            "title": "小明是用户的朋友",
            "content": "小明和用户一起工作",
            "hybrid_score": 0.6,
            "vector_score": 0.6,
            "rank_score": 0.6,
            "memory_type": "relationship",
        }
        enriched = _enrich_related_entities(entities=entities, memories=[high_rel_memory])
        self.assertGreater(len(enriched[0]["relationship_reasons"]), 0)


class NegationPatternTests(unittest.TestCase):
    def _decide(self, user_message: str) -> dict:
        from service.mcp_server import _decide_recall
        return _decide_recall(
            user_message=user_message,
            draft_response=None,
            topic_hint=None,
            memories=[],
            contexts=[],
        )

    def test_negated_like_does_not_trigger(self) -> None:
        # "不喜欢" 前 2 字含否定词，不应触发
        result = self._decide("我不喜欢这个")
        self.assertFalse(result["should_recall"])

    def test_positive_like_triggers(self) -> None:
        from service.mcp_server import _has_negated_pattern, PERSONAL_QUERY_PATTERNS
        self.assertTrue(_has_negated_pattern("我喜欢咖啡", PERSONAL_QUERY_PATTERNS))

    def test_negation_not_in_prefix_still_matches(self) -> None:
        # 否定词不在紧前 2 字，仍命中
        from service.mcp_server import _has_negated_pattern, PERSONAL_QUERY_PATTERNS
        self.assertTrue(_has_negated_pattern("完全不知道我喜欢什么", PERSONAL_QUERY_PATTERNS))


class PhraseStopwordTests(unittest.TestCase):
    def test_stopword_phrase_does_not_score(self) -> None:
        from service.mcp_server import _shared_phrase_relevance
        # "工作" 是停用词，不应计分
        score = _shared_phrase_relevance("我今天工作很忙", "工作")
        self.assertEqual(0.0, score)

    def test_non_stopword_phrase_scores(self) -> None:
        from service.mcp_server import _shared_phrase_relevance
        # "咖啡" 不是停用词，应有分数
        score = _shared_phrase_relevance("我喜欢咖啡", "咖啡")
        self.assertGreater(score, 0.0)


class TurnCountTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        from service import mcp_server
        self.server = mcp_server.create_server()

    @patch("service.mcp_server.sync_session_context")
    @patch("service.mcp_server.run_capture_cycle")
    @patch("service.mcp_server.search_recent_context_summaries")
    @patch("service.mcp_server.search_context_snapshots")
    @patch("service.mcp_server.search_memories")
    async def test_sync_every_n_turns_skips_sync_on_non_nth_turn(
        self,
        search_memories_mock,
        search_context_mock,
        recent_context_mock,
        run_capture_cycle_mock,
        sync_session_context_mock,
    ) -> None:
        search_memories_mock.return_value = []
        search_context_mock.return_value = []
        recent_context_mock.return_value = []
        run_capture_cycle_mock.return_value = {
            "event_count": 1, "analysis_result_count": 0, "persisted_count": 0
        }
        sync_session_context_mock.return_value = {
            "event_count": 0, "segment_snapshot": None,
            "topic_snapshot": None, "global_topic_snapshot": None, "memory_sync": None,
        }

        # 重置 turn 计数（隔离测试）
        import service.mcp_server as mcp_srv
        mcp_srv._session_turn_counts.pop("test-sync-n", None)

        # 第 1 轮（N=3 时，不是第 N 轮），不应触发 sync
        await self.server.call_tool(
            "orchestrate_turn_memory",
            {
                "user_message": "第一轮消息",
                "assistant_text": "回复一",
                "session_key": "test-sync-n",
                "capture_after_response": True,
                "sync_every_n_turns": 3,
            },
        )
        # sync_session_context 不应在 sync_every_n_turns=3 且第 1 轮时被调用
        sync_session_context_mock.assert_not_called()


class RecallWeightConfigTests(unittest.TestCase):
    def test_recall_score_weights_exist_in_constants(self) -> None:
        from service.constants import RECALL_SCORE_WEIGHTS
        required_keys = [
            "high_confidence_memory", "usable_memory_match", "explicit_memory",
            "strong_semantic", "moderate_semantic", "personal_memory_signal",
            "personal_query_signal", "topic_continuity",
        ]
        for key in required_keys:
            self.assertIn(key, RECALL_SCORE_WEIGHTS)

    def test_env_override_changes_weight(self) -> None:
        import os
        import importlib
        os.environ["LYB_SKILL_MEMORY_WEIGHT_HIGH_CONF"] = "0.99"
        try:
            import service.constants
            importlib.reload(service.constants)
            from service.constants import RECALL_SCORE_WEIGHTS
            self.assertAlmostEqual(0.99, RECALL_SCORE_WEIGHTS["high_confidence_memory"])
        finally:
            del os.environ["LYB_SKILL_MEMORY_WEIGHT_HIGH_CONF"]
            importlib.reload(service.constants)


if __name__ == "__main__":
    unittest.main()
