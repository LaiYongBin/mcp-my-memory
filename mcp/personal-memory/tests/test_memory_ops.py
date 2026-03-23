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
        from unittest.mock import patch, MagicMock, call
        from service.memory_ops import merge_duplicate_memories

        # _get_memories_batch 内部会调用 apply_memory_governance，直接透传即可
        with patch("service.memory_ops.apply_memory_governance", side_effect=lambda x: x), \
             patch("service.memory_ops.get_conn") as mock_conn:
            mock_cursor = MagicMock()
            # 第一次 fetchall：find_duplicate_pairs 返回候选对
            # 第二次 fetchall：_get_memories_batch 返回完整记忆行
            mock_cursor.fetchall.side_effect = [
                [{"master_candidate_id": 1, "slave_candidate_id": 2, "distance": 0.05}],
                [
                    {"id": 1, "confidence": 0.8, "updated_at": "2026-01-01",
                     "content": "内容1", "tags": [], "status": "active",
                     "user_code": "LYB", "memory_type": None, "category": None,
                     "title": "记忆1", "summary": None, "source_type": None,
                     "source_ref": None, "importance": 5, "is_explicit": False,
                     "supersedes_id": None, "conflict_with_id": None,
                     "valid_from": None, "valid_to": None, "subject_key": None,
                     "related_subject_key": None, "attribute_key": None, "value_text": None,
                     "conflict_scope": None, "sensitivity_level": None,
                     "disclosure_policy": None, "lifecycle_state": None,
                     "stability_score": None, "recall_count": 0, "last_recalled_at": None,
                     "created_at": None, "deleted_at": None},
                    {"id": 2, "confidence": 0.8, "updated_at": "2026-01-01",
                     "content": "内容2", "tags": [], "status": "active",
                     "user_code": "LYB", "memory_type": None, "category": None,
                     "title": "记忆2", "summary": None, "source_type": None,
                     "source_ref": None, "importance": 5, "is_explicit": False,
                     "supersedes_id": None, "conflict_with_id": None,
                     "valid_from": None, "valid_to": None, "subject_key": None,
                     "related_subject_key": None, "attribute_key": None, "value_text": None,
                     "conflict_scope": None, "sensitivity_level": None,
                     "disclosure_policy": None, "lifecycle_state": None,
                     "stability_score": None, "recall_count": 0, "last_recalled_at": None,
                     "created_at": None, "deleted_at": None},
                ],
            ]
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
            mock_conn.return_value.__enter__.return_value.commit.return_value = None

            with patch("service.memory_ops.merge_memory_pair") as mock_merge:
                mock_merge.return_value = {"master_id": 1, "slave_id": 2, "dry_run": True}
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


class SubmitChallengeAnswerTests(unittest.TestCase):
    def test_submit_challenge_answer_exists(self):
        from service.memory_ops import submit_challenge_answer
        self.assertTrue(callable(submit_challenge_answer))


class MemoryTimelineTests(unittest.TestCase):
    def test_get_memory_timeline_exists(self) -> None:
        from service.memory_ops import get_memory_timeline
        self.assertTrue(callable(get_memory_timeline))

    def test_circular_reference_protection(self) -> None:
        """循环引用时不应无限循环。"""
        from unittest.mock import patch, MagicMock
        from service.memory_ops import get_memory_timeline

        mem1 = {"id": 1, "user_code": "LYB", "supersedes_id": 2, "updated_at": "2026-01-02", "title": "v2"}
        mem2 = {"id": 2, "user_code": "LYB", "supersedes_id": 1, "updated_at": "2026-01-01", "title": "v1"}

        def fake_get_memory(mid, uc):
            return {1: mem1, 2: mem2}.get(mid)

        with patch("service.memory_ops.get_memory", side_effect=fake_get_memory), \
             patch("service.memory_ops._fetch_where_supersedes_id", return_value=None), \
             patch("service.memory_ops.get_conn") as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = mem1
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
            result = get_memory_timeline(user_code="LYB", memory_id=1, limit=10)
            self.assertIsInstance(result, list)

    def test_empty_for_nonexistent_memory(self) -> None:
        from unittest.mock import patch
        from service.memory_ops import get_memory_timeline

        with patch("service.memory_ops.get_memory", return_value=None):
            result = get_memory_timeline(user_code="LYB", memory_id=999, limit=10)
            self.assertEqual([], result)


class FetchSourceTurnsTests(unittest.TestCase):
    def test_fetch_source_turns_exists(self) -> None:
        from service.memory_ops import fetch_source_turns
        self.assertTrue(callable(fetch_source_turns))

    def test_exact_ref_parsed_correctly(self) -> None:
        from unittest.mock import patch, MagicMock
        from service.memory_ops import fetch_source_turns

        with patch("service.memory_ops.get_conn") as mock_conn:
            mock_cursor = MagicMock()
            fake_turn = {"id": 42, "content": "用户说了什么", "role": "user", "session_key": "s1"}
            mock_cursor.fetchall.return_value = [fake_turn]
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor

            result = fetch_source_turns(["s1:42"])
            self.assertIn("s1:42", result)
            self.assertEqual(42, result["s1:42"]["id"])

    def test_empty_refs_returns_empty(self) -> None:
        from service.memory_ops import fetch_source_turns
        result = fetch_source_turns([])
        self.assertEqual({}, result)


class ExportMemoriesTests(unittest.TestCase):
    def test_export_result_schema_exists(self) -> None:
        from service.schemas import ExportResult
        result = ExportResult(
            records=[{"id": 1}],
            export_count=1,
            sensitivity_levels_included=["public"],
        )
        self.assertEqual(1, result.export_count)

    def test_internal_only_excluded(self) -> None:
        """disclosure_policy='internal_only' 的记忆不应出现在导出结果中。"""
        from unittest.mock import patch, MagicMock
        from service.memory_ops import export_memory_records

        with patch("service.memory_ops.get_conn") as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = [
                {"id": 1, "disclosure_policy": "normal", "sensitivity_level": "normal", "title": "正常记忆"}
            ]
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
            result = export_memory_records(user_code="LYB")
            self.assertEqual(1, len(result["records"]))

    def test_null_disclosure_policy_not_excluded(self) -> None:
        """disclosure_policy IS NULL 的记忆（视为 normal）应被包含。"""
        from unittest.mock import patch, MagicMock
        from service.memory_ops import export_memory_records

        with patch("service.memory_ops.get_conn") as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = [
                {"id": 2, "disclosure_policy": None, "sensitivity_level": "normal", "title": "无策略记忆"}
            ]
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
            result = export_memory_records(user_code="LYB")
            self.assertEqual(1, len(result["records"]))


class MemoryReportTests(unittest.TestCase):
    def test_memory_report_schema_exists(self) -> None:
        from service.schemas import MemoryReport
        report = MemoryReport(
            period_days=30,
            new_memories_by_category={},
            updated_count=0,
            stale_count=0,
            explicit_count=0,
            top_recalled=[],
        )
        self.assertEqual(30, report.period_days)

    def test_generate_report_returns_zeros_for_empty(self) -> None:
        from unittest.mock import patch, MagicMock
        from service.memory_ops import generate_memory_report

        with patch("service.memory_ops.get_conn") as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_cursor.fetchone.return_value = {"count": 0}
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
            result = generate_memory_report(user_code="LYB", period_days=30)
            self.assertEqual(30, result["period_days"])
            self.assertIn("new_memories_by_category", result)
            self.assertIn("stale_count", result)


    def test_memory_report_has_sentiment_distribution(self):
        from unittest.mock import patch, MagicMock
        from service.memory_ops import generate_memory_report

        with patch("service.memory_ops.get_conn") as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_cursor.fetchone.return_value = {"count": 0, "cnt": 0}
            mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
            result = generate_memory_report(user_code="__nonexistent__")
        self.assertIn("sentiment_distribution", result)
        self.assertIsInstance(result["sentiment_distribution"], dict)


class RevertMemoryToVersionTests(unittest.TestCase):
    def test_revert_memory_to_version_exists(self):
        from service.memory_ops import revert_memory_to_version
        self.assertTrue(callable(revert_memory_to_version))


class TaxonomyNormalizeCacheTests(unittest.TestCase):
    def test_lookup_domain_value_is_cached(self):
        """lookup_domain_value 应使用 lru_cache，相同参数不重复查库。"""
        from service.domain_registry import lookup_domain_value
        self.assertTrue(hasattr(lookup_domain_value, "cache_info"),
                        "lookup_domain_value 应具有 lru_cache 的 cache_info 属性")

    def test_lookup_domain_alias_is_cached(self):
        """lookup_domain_alias 应使用 lru_cache，相同参数不重复查库。"""
        from service.domain_registry import lookup_domain_alias
        self.assertTrue(hasattr(lookup_domain_alias, "cache_info"),
                        "lookup_domain_alias 应具有 lru_cache 的 cache_info 属性")


class MarkMemoriesRecalledBatchTests(unittest.TestCase):
    def test_lifecycle_state_updated_in_single_query(self):
        """lifecycle_state 更新应合并为单次批量 SQL，而非逐条执行。"""
        from service import memory_ops
        from unittest.mock import patch, MagicMock, call
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor = MagicMock(return_value=mock_cur)
        # 模拟返回 3 条记忆的 recall 更新结果
        mock_cur.fetchall.return_value = [
            {"id": 1, "confidence": 0.8, "is_explicit": False, "memory_type": "fact",
             "status": "active", "valid_to": None, "conflict_with_id": None,
             "updated_at": None, "recall_count": 5, "stability_score": 0.7},
            {"id": 2, "confidence": 0.6, "is_explicit": False, "memory_type": "fact",
             "status": "active", "valid_to": None, "conflict_with_id": None,
             "updated_at": None, "recall_count": 2, "stability_score": 0.5},
            {"id": 3, "confidence": 0.9, "is_explicit": True, "memory_type": "preference",
             "status": "active", "valid_to": None, "conflict_with_id": None,
             "updated_at": None, "recall_count": 10, "stability_score": 0.9},
        ]
        with patch("service.memory_ops.get_conn", return_value=mock_conn), \
             patch("service.memory_ops._resolve_user", return_value="test"):
            memory_ops.mark_memories_recalled([1, 2, 3], "test")
        # 核心断言：execute 调用次数应为 2（recall_count 批量 + lifecycle_state 批量 CASE WHEN）
        # 而非 4（1 + 3 次逐条）
        self.assertEqual(mock_cur.execute.call_count, 2,
                         f"应只执行 2 次 SQL（当前执行了 {mock_cur.execute.call_count} 次），lifecycle_state 应用 CASE WHEN 批量更新")


# 完整字段 dummy_row，与 RETURNING * 扩展后一致
_DUMMY_MEMORY_ROW = {
    "id": 42, "user_code": "test", "title": "test", "content": "test content",
    "memory_type": "fact", "category": "context", "summary": None,
    "tags": [], "source_type": "manual", "source_ref": None,
    "confidence": 0.7, "importance": 5, "status": "active",
    "is_explicit": False, "valid_from": None, "valid_to": None,
    "subject_key": None, "related_subject_key": None, "attribute_key": None,
    "value_text": None, "conflict_scope": None, "sensitivity_level": "normal",
    "disclosure_policy": None, "lifecycle_state": "active", "stability_score": 0.5,
    "conflict_with_id": None, "supersedes_id": None,
    "created_at": None, "updated_at": None, "last_recalled_at": None,
    "deleted_at": None, "recall_count": 0,
}


class UpsertMemoryReturningTests(unittest.TestCase):
    def test_upsert_memory_does_not_call_get_memory_after_write(self):
        """upsert_memory 写入后不应再调用 get_memory 做额外 SELECT。"""
        from service import memory_ops
        from unittest.mock import patch, MagicMock
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor = MagicMock(return_value=mock_cur)
        mock_cur.fetchone.return_value = _DUMMY_MEMORY_ROW
        with patch("service.memory_ops.get_conn", return_value=mock_conn), \
             patch("service.memory_ops._resolve_user", return_value="test"), \
             patch("service.memory_ops.find_existing_memory", return_value=None), \
             patch("service.memory_ops._normalize_memory_taxonomy", return_value={
                 "memory_type": "fact", "source_type": "manual",
                 "category": "context", "attribute_key": None,
             }), \
             patch("service.memory_ops.apply_memory_governance", side_effect=lambda x: {
                 **x,
                 "sensitivity_level": x.get("sensitivity_level", "normal"),
                 "disclosure_policy": x.get("disclosure_policy", None),
                 "lifecycle_state": x.get("lifecycle_state", "active"),
                 "stability_score": x.get("stability_score", 0.5),
             }), \
             patch("service.memory_ops.get_memory") as mock_get_memory, \
             patch("service.memory_ops.refresh_memory_embedding"), \
             patch("service.memory_ops.sync_entity_graph_for_memory"):
            memory_ops.upsert_memory({
                "title": "test", "content": "test content",
                "memory_type": "fact", "user_code": "test",
            })
            mock_get_memory.assert_not_called()


class UpsertMemoryDeferEmbeddingTests(unittest.TestCase):
    def test_defer_embedding_skips_refresh_memory_embedding(self):
        """defer_embedding=True 时 upsert_memory 不应调用 refresh_memory_embedding。"""
        from service import memory_ops
        from unittest.mock import patch, MagicMock
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor = MagicMock(return_value=mock_cur)
        # 返回完整行（C4 已修改 RETURNING *，此处 mock 要覆盖完整字段）
        mock_cur.fetchone.return_value = {
            "id": 1, "user_code": "test", "title": "t", "content": "c",
            "memory_type": "fact", "category": None, "summary": None,
            "tags": [], "source_type": "manual", "source_ref": None,
            "confidence": 0.7, "importance": 5, "status": "active",
            "is_explicit": False, "valid_from": None, "valid_to": None,
            "subject_key": None, "related_subject_key": None, "attribute_key": None,
            "value_text": None, "conflict_scope": None, "sensitivity_level": "normal",
            "disclosure_policy": None, "lifecycle_state": "active", "stability_score": 0.5,
            "conflict_with_id": None, "supersedes_id": None,
            "created_at": None, "updated_at": None, "last_recalled_at": None,
            "deleted_at": None, "recall_count": 0,
        }
        with patch("service.memory_ops.get_conn", return_value=mock_conn), \
             patch("service.memory_ops._resolve_user", return_value="test"), \
             patch("service.memory_ops.find_existing_memory", return_value=None), \
             patch("service.memory_ops._normalize_memory_taxonomy", return_value={
                 "memory_type": "fact", "source_type": "manual",
                 "category": "context", "attribute_key": None,
             }), \
             patch("service.memory_ops.apply_memory_governance", side_effect=lambda x: {
                 **x,
                 "sensitivity_level": x.get("sensitivity_level", "normal"),
                 "disclosure_policy": x.get("disclosure_policy", None),
                 "lifecycle_state": x.get("lifecycle_state", "active"),
                 "stability_score": x.get("stability_score", 0.5),
             }), \
             patch("service.memory_ops.refresh_memory_embedding") as mock_embed, \
             patch("service.memory_ops.sync_entity_graph_for_memory"):
            memory_ops.upsert_memory(
                {"title": "t", "content": "c", "memory_type": "fact"},
                defer_embedding=True,
            )
            mock_embed.assert_not_called()


class SearchMemoriesFilterTests(unittest.TestCase):
    def test_search_memories_accepts_subject_key_param(self):
        """search_memories 应接受 subject_key 过滤参数。"""
        import inspect
        from service.memory_ops import search_memories
        sig = inspect.signature(search_memories)
        self.assertIn("subject_key", sig.parameters,
                      "search_memories 应支持 subject_key 参数")

    def test_search_memories_accepts_attribute_key_param(self):
        """search_memories 应接受 attribute_key 过滤参数。"""
        import inspect
        from service.memory_ops import search_memories
        sig = inspect.signature(search_memories)
        self.assertIn("attribute_key", sig.parameters,
                      "search_memories 应支持 attribute_key 参数")


class GetDomainDefinitionCacheTests(unittest.TestCase):
    def test_get_domain_definition_is_cached(self):
        """get_domain_definition 应使用 lru_cache，相同参数不重复查库。"""
        from service.domain_registry import get_domain_definition
        self.assertTrue(hasattr(get_domain_definition, "cache_info"),
                        "get_domain_definition 应具有 lru_cache 的 cache_info 属性")


class ArchiveMemoryEfficiencyTests(unittest.TestCase):
    def test_archive_memory_does_not_call_get_memory(self):
        """archive_memory 应只执行一次 SQL（UPDATE RETURNING），不再调用 get_memory。"""
        from service import memory_ops
        from unittest.mock import patch, MagicMock
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor = MagicMock(return_value=mock_cur)
        mock_cur.fetchone.return_value = {
            "id": 1, "user_code": "test", "title": "t", "content": "c",
            "memory_type": "fact", "category": None, "summary": None,
            "tags": [], "source_type": "manual", "source_ref": None,
            "confidence": 0.7, "importance": 5, "status": "archived",
            "is_explicit": False, "valid_from": None, "valid_to": None,
            "subject_key": None, "related_subject_key": None, "attribute_key": None,
            "value_text": None, "conflict_scope": None, "sensitivity_level": "normal",
            "disclosure_policy": None, "lifecycle_state": "active", "stability_score": 0.5,
            "sentiment": None, "conflict_with_id": None, "supersedes_id": None,
            "created_at": None, "updated_at": None, "last_recalled_at": None,
            "deleted_at": None, "recall_count": 0,
        }
        with patch("service.memory_ops.get_conn", return_value=mock_conn), \
             patch("service.memory_ops._resolve_user", return_value="test"), \
             patch("service.memory_ops.get_memory") as mock_get_memory, \
             patch("service.memory_ops.refresh_entity_graph_for_subject"):
            memory_ops.archive_memory(1, "test")
            mock_get_memory.assert_not_called()


class MaintainMemoryStoreBatchTests(unittest.TestCase):
    def test_maintain_memory_store_uses_single_batch_update(self):
        """maintain_memory_store 非 dry_run 时应合并为单次批量 SQL，而非逐条 UPDATE。"""
        from service import memory_ops
        from unittest.mock import patch, MagicMock
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor = MagicMock(return_value=mock_cur)
        # 3 条记忆，lifecycle_state 从 "stale" 变为 "active" 均需更新
        rows = [
            {"id": i, "user_code": "test", "title": f"t{i}", "content": f"c{i}",
             "memory_type": "fact", "category": "context", "summary": None,
             "tags": [], "source_type": "manual", "source_ref": None,
             "confidence": 0.7, "importance": 5, "status": "active",
             "is_explicit": False, "valid_from": None, "valid_to": None,
             "subject_key": None, "related_subject_key": None, "attribute_key": None,
             "value_text": None, "conflict_scope": None, "sensitivity_level": "normal",
             "disclosure_policy": None, "lifecycle_state": "stale",
             "stability_score": 0.2, "sentiment": None, "conflict_with_id": None,
             "supersedes_id": None, "created_at": None, "updated_at": None,
             "last_recalled_at": None, "deleted_at": None, "recall_count": 0}
            for i in range(1, 4)
        ]
        mock_cur.fetchall.return_value = rows
        with patch("service.memory_ops.get_conn", return_value=mock_conn), \
             patch("service.memory_ops._resolve_user", return_value="test"), \
             patch("service.memory_ops.apply_memory_governance",
                   side_effect=lambda r: {**r, "lifecycle_state": "active",
                                          "stability_score": 0.5,
                                          "sensitivity_level": "normal",
                                          "disclosure_policy": None}):
            memory_ops.maintain_memory_store(user_code="test", dry_run=False,
                                              auto_archive_stale_days=0, auto_resolve_review_days=0)
        # 核心断言：execute 调用次数应为 2（1次 SELECT + 1次批量 UPDATE）
        # 而非 4（1次 SELECT + 3次逐条 UPDATE）
        self.assertEqual(mock_cur.execute.call_count, 2,
                         f"应只执行 2 次 SQL，但实际执行了 {mock_cur.execute.call_count} 次")


if __name__ == "__main__":
    unittest.main()


class UpsertMemoryGovernanceTests(unittest.TestCase):
    def test_upsert_memory_calls_governance_once(self):
        """upsert_memory 应只调用一次 apply_memory_governance（消除冗余调用）。"""
        from service import memory_ops
        from unittest.mock import patch, MagicMock

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor = MagicMock(return_value=mock_cur)
        mock_row = {
            "id": 1, "user_code": "test", "title": "t", "content": "c",
            "memory_type": "fact", "category": None, "summary": None,
            "tags": [], "source_type": "manual", "source_ref": None,
            "confidence": 0.7, "importance": 5, "status": "active",
            "is_explicit": False, "valid_from": None, "valid_to": None,
            "subject_key": None, "related_subject_key": None, "attribute_key": None,
            "value_text": None, "conflict_scope": None, "sensitivity_level": "normal",
            "disclosure_policy": None, "lifecycle_state": "active", "stability_score": 0.5,
            "sentiment": None, "conflict_with_id": None, "supersedes_id": None,
            "created_at": None, "updated_at": None, "last_recalled_at": None,
            "deleted_at": None, "recall_count": 0,
        }
        mock_cur.fetchone.return_value = mock_row

        with patch("service.memory_ops.get_conn", return_value=mock_conn), \
             patch("service.memory_ops._resolve_user", return_value="test"), \
             patch("service.memory_ops.find_existing_memory", return_value=None), \
             patch("service.memory_ops._normalize_memory_taxonomy", return_value={
                 "memory_type": "fact", "source_type": "manual",
                 "category": "context", "attribute_key": "",
             }), \
             patch("service.memory_ops.apply_memory_governance",
                   side_effect=lambda x: {**x, "_governed": True,
                                          "sensitivity_level": "normal",
                                          "disclosure_policy": "normal",
                                          "lifecycle_state": "active",
                                          "stability_score": 0.5}) as mock_gov, \
             patch("service.memory_ops._entity_graph_executor") as mock_exec, \
             patch("service.memory_ops.refresh_memory_embedding"):
            mock_exec.submit = MagicMock()
            memory_ops.upsert_memory({"title": "t", "content": "c"}, defer_embedding=True)

        # 关键断言：apply_memory_governance 应被调用 2 次（预处理 + RETURNING），
        # 而不是 3 次（第三次是冗余的 return apply_memory_governance(result)）
        self.assertEqual(mock_gov.call_count, 2,
                         f"apply_memory_governance 应被调用 2 次，实际 {mock_gov.call_count} 次")


class MarkMemoriesRecalledTests(unittest.TestCase):
    def test_lifecycle_update_uses_unnest_not_case_when(self):
        """mark_memories_recalled 的 lifecycle_state 更新应使用 UNNEST，不应用字符串拼接的 CASE WHEN。"""
        import inspect
        from service import memory_ops
        source = inspect.getsource(memory_ops.mark_memories_recalled)
        self.assertNotIn("CASE WHEN id =", source,
                         "mark_memories_recalled 不应在 SQL 中用字符串拼接嵌入 id（安全风险）")
        self.assertIn("UNNEST", source,
                      "mark_memories_recalled 应使用 UNNEST 批量更新 lifecycle_state")


class DomainCacheInvalidationTests(unittest.TestCase):
    def test_create_domain_value_clears_lookup_cache(self):
        """_create_domain_value 写入后应清除 lookup_domain_value 缓存。"""
        import inspect
        from service import domain_registry
        source = inspect.getsource(domain_registry._create_domain_value)
        self.assertIn("cache_clear", source,
                      "_create_domain_value 应在写入后调用 lookup_domain_value.cache_clear()")

    def test_upsert_domain_alias_clears_lookup_cache(self):
        """_upsert_domain_alias 写入后应清除 lookup_domain_alias 缓存。"""
        import inspect
        from service import domain_registry
        source = inspect.getsource(domain_registry._upsert_domain_alias)
        self.assertIn("cache_clear", source,
                      "_upsert_domain_alias 应在写入后调用 lookup_domain_alias.cache_clear()")


class EntityGraphAsyncTests(unittest.TestCase):
    def test_upsert_memory_does_not_block_on_entity_graph(self):
        """upsert_memory 调用后 sync_entity_graph_for_memory 应在后台执行，不阻塞主流程。"""
        import inspect
        from service import memory_ops
        source = inspect.getsource(memory_ops.upsert_memory)
        self.assertNotIn("sync_entity_graph_for_memory(result)", source,
                         "upsert_memory 不应同步调用 sync_entity_graph_for_memory，应改为 fire-and-forget")


class HybridSearchFilterTests(unittest.TestCase):
    def test_search_memories_hybrid_accepts_subject_key(self):
        """_search_memories_hybrid 应接受 subject_key 参数。"""
        import inspect
        from service.memory_ops import _search_memories_hybrid
        sig = inspect.signature(_search_memories_hybrid)
        self.assertIn("subject_key", sig.parameters,
                      "_search_memories_hybrid 应支持 subject_key 过滤参数")

    def test_search_memories_hybrid_accepts_attribute_key(self):
        """_search_memories_hybrid 应接受 attribute_key 参数。"""
        import inspect
        from service.memory_ops import _search_memories_hybrid
        sig = inspect.signature(_search_memories_hybrid)
        self.assertIn("attribute_key", sig.parameters,
                      "_search_memories_hybrid 应支持 attribute_key 过滤参数")

    def test_search_memories_hybrid_accepts_sentiment(self):
        """_search_memories_hybrid 应接受 sentiment 参数。"""
        import inspect
        from service.memory_ops import _search_memories_hybrid
        sig = inspect.signature(_search_memories_hybrid)
        self.assertIn("sentiment", sig.parameters,
                      "_search_memories_hybrid 应支持 sentiment 过滤参数")

    def test_search_memories_forwards_all_filters_to_hybrid(self):
        """search_memories 调用 _search_memories_hybrid 时应透传所有过滤参数。"""
        import inspect
        from service import memory_ops
        source = inspect.getsource(memory_ops.search_memories)
        self.assertIn("subject_key=subject_key", source,
                      "search_memories 调用 _search_memories_hybrid 应透传 subject_key")
        self.assertIn("attribute_key=attribute_key", source,
                      "search_memories 调用 _search_memories_hybrid 应透传 attribute_key")
        self.assertIn("sentiment=sentiment", source,
                      "search_memories 调用 _search_memories_hybrid 应透传 sentiment")


class PaginationTests(unittest.TestCase):
    def test_search_memories_accepts_offset(self):
        """search_memories 应接受 offset 分页参数。"""
        import inspect
        from service.memory_ops import search_memories
        sig = inspect.signature(search_memories)
        self.assertIn("offset", sig.parameters,
                      "search_memories 应支持 offset 参数")

    def test_search_memories_by_time_range_accepts_offset(self):
        """search_memories_by_time_range 应接受 offset 分页参数。"""
        import inspect
        from service.memory_ops import search_memories_by_time_range
        sig = inspect.signature(search_memories_by_time_range)
        self.assertIn("offset", sig.parameters,
                      "search_memories_by_time_range 应支持 offset 参数")


class RecentMemoryContextCacheTests(unittest.TestCase):
    def test_recent_memory_context_is_cached(self):
        """相同 user_code 在 TTL 内应命中缓存，不重复查库。"""
        from service import analyzer
        self.assertTrue(hasattr(analyzer, "_recent_memory_cache"),
                        "_recent_memory_cache 应是模块级缓存字典")

    def test_cache_returns_same_result_without_db(self):
        from unittest.mock import patch, MagicMock
        from service import analyzer
        # 清空缓存
        analyzer._recent_memory_cache.clear()
        with patch("service.analyzer.get_conn") as mock_conn:
            mock_cur = MagicMock()
            mock_cur.__enter__ = MagicMock(return_value=mock_cur)
            mock_cur.__exit__ = MagicMock(return_value=False)
            mock_conn.return_value.__enter__ = MagicMock(return_value=mock_conn.return_value)
            mock_conn.return_value.__exit__ = MagicMock(return_value=False)
            mock_conn.return_value.cursor.return_value = mock_cur
            mock_cur.fetchall.return_value = [{"id": 1, "title": "t"}]
            result1 = analyzer._recent_memory_context("test_user")
            result2 = analyzer._recent_memory_context("test_user")
            # 第二次应命中缓存，只查一次 DB
            self.assertEqual(mock_cur.execute.call_count, 1)
            self.assertEqual(result1, result2)


class AccumulateEvidenceBatchTests(unittest.TestCase):
    def test_accumulate_evidence_batch_exists(self):
        from service.evidence import accumulate_evidence_batch
        self.assertTrue(callable(accumulate_evidence_batch))

    def test_batch_returns_list_same_length(self):
        """返回列表长度应与输入 items 一致。"""
        from unittest.mock import patch, MagicMock
        from service.evidence import accumulate_evidence_batch
        with patch("service.evidence.get_conn") as mock_conn:
            mock_cur = MagicMock()
            mock_cur.__enter__ = MagicMock(return_value=mock_cur)
            mock_cur.__exit__ = MagicMock(return_value=False)
            mock_conn.return_value.__enter__ = MagicMock(return_value=mock_conn.return_value)
            mock_conn.return_value.__exit__ = MagicMock(return_value=False)
            mock_conn.return_value.cursor.return_value = mock_cur
            mock_cur.fetchall.return_value = []
            mock_cur.fetchone.return_value = {
                "id": 1, "user_code": "test", "category": "preference",
                "subject_key": "user", "attribute_key": "drink", "value_text": "coffee",
                "latest_claim": "喜欢咖啡", "conflict_scope": "user.drink",
                "evidence_type": "explicit", "time_scope": "long_term",
                "support_score": 0.5, "occurrence_count": 1,
                "promoted_memory_id": None, "status": "active", "tags": [],
                "first_seen_at": None, "last_seen_at": None,
                "created_at": None, "updated_at": None,
            }
            items = [
                {"subject": "user", "attribute": "drink", "value": "coffee",
                 "claim": "喜欢���啡", "confidence": 0.8, "evidence_type": "explicit",
                 "time_scope": "long_term", "category": "preference", "conflict_scope": "user.drink"},
                {"subject": "user", "attribute": "food", "value": "rice",
                 "claim": "喜欢米饭", "confidence": 0.7, "evidence_type": "observed",
                 "time_scope": "long_term", "category": "preference", "conflict_scope": "user.food"},
            ]
            result = accumulate_evidence_batch(user_code="test", items=items)
            self.assertEqual(2, len(result), "返回列表长度应与输入等长")

    def test_empty_items_returns_empty(self):
        from service.evidence import accumulate_evidence_batch
        result = accumulate_evidence_batch(user_code="test", items=[])
        self.assertEqual([], result)


class StabilityScoreDecayTests(unittest.TestCase):
    def _make_item(self, attribute_key: str, age_days: int, confidence: float = 0.8) -> dict:
        from datetime import datetime, timezone, timedelta
        return {
            "confidence": confidence,
            "is_explicit": False,
            "recall_count": 0,
            "attribute_key": attribute_key,
            "updated_at": (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat(),
        }

    def test_current_goal_decays_faster_at_30_days(self):
        """current_goal 属性 30 天后稳定性应明显低于通用属性。"""
        from service.memory_governance import derive_stability_score
        generic_30 = derive_stability_score(self._make_item("drink", 30))
        goal_30 = derive_stability_score(self._make_item("current_goal", 30))
        self.assertLess(goal_30, generic_30, "current_goal 30天应比通用属性衰减更多")

    def test_current_goal_at_60_days_is_below_threshold(self):
        """current_goal 60 天后稳定性应低于 0.5（视为过时）。"""
        from service.memory_governance import derive_stability_score
        score = derive_stability_score(self._make_item("current_goal", 60, confidence=0.75))
        self.assertLess(score, 0.5)

    def test_generic_120_days_has_stronger_penalty(self):
        """通用属性 120 天 age_penalty 应从 0.18 增大到至少 0.30。"""
        from service.memory_governance import derive_stability_score
        from datetime import datetime, timezone, timedelta
        item_0 = {"confidence": 0.7, "is_explicit": False, "recall_count": 0, "attribute_key": "drink"}
        item_120 = {
            "confidence": 0.7, "is_explicit": False, "recall_count": 0,
            "attribute_key": "drink",
            "updated_at": (datetime.now(timezone.utc) - timedelta(days=120)).isoformat(),
        }
        score_0 = derive_stability_score(item_0)
        score_120 = derive_stability_score(item_120)
        self.assertLess(score_120, score_0 - 0.25,
                        "120天通用属性 age_penalty 应至少 0.30")


class SupersededMemoryConfidenceTests(unittest.TestCase):
    def test_superseded_memory_has_lower_confidence(self):
        """supersedes_id 不为空的记忆（旧版本）应自动降低 confidence。"""
        from service.memory_governance import apply_memory_governance
        item = {
            "confidence": 0.9,
            "is_explicit": True,
            "recall_count": 0,
            "supersedes_id": 42,
            "conflict_with_id": None,
            "status": "active",
        }
        governed = apply_memory_governance(item)
        self.assertLessEqual(governed["confidence"], 0.35,
                             "被替代的记忆 confidence 应降至 <= 0.35")

    def test_conflicted_memory_has_lower_confidence(self):
        """conflict_with_id 不为空的记忆应自动降低 confidence。"""
        from service.memory_governance import apply_memory_governance
        item = {
            "confidence": 0.85,
            "is_explicit": False,
            "recall_count": 0,
            "supersedes_id": None,
            "conflict_with_id": 7,
            "status": "active",
        }
        governed = apply_memory_governance(item)
        self.assertLessEqual(governed["confidence"], 0.45)

    def test_normal_memory_keeps_confidence(self):
        """无冲突、未被替代的记忆 confidence 不应被降低。"""
        from service.memory_governance import apply_memory_governance
        item = {
            "confidence": 0.85,
            "is_explicit": True,
            "recall_count": 3,
            "supersedes_id": None,
            "conflict_with_id": None,
            "status": "active",
        }
        governed = apply_memory_governance(item)
        self.assertGreaterEqual(governed["confidence"], 0.80)


class AutoArchiveStaleTests(unittest.TestCase):
    def test_maintain_accepts_auto_archive_stale_days(self):
        import inspect
        from service.memory_ops import maintain_memory_store
        sig = inspect.signature(maintain_memory_store)
        self.assertIn("auto_archive_stale_days", sig.parameters,
                      "maintain_memory_store 应接受 auto_archive_stale_days 参数")

    def test_maintenance_result_has_auto_archived_count(self):
        from service.schemas import MaintenanceResult
        result = MaintenanceResult(
            scanned_count=5,
            updated_count=2,
            dry_run=False,
            changed_ids=[1, 2],
            lifecycle_counts={},
            updated_memories=[],
            filter_applied={},
            auto_archived_count=3,
        )
        self.assertEqual(3, result.auto_archived_count)


class ReviewCandidateTimeoutTests(unittest.TestCase):
    def test_maintain_accepts_auto_resolve_review_days(self):
        import inspect
        from service.memory_ops import maintain_memory_store
        sig = inspect.signature(maintain_memory_store)
        self.assertIn("auto_resolve_review_days", sig.parameters,
                      "maintain_memory_store 应接受 auto_resolve_review_days 参数")


class ContextSearchOffsetTests(unittest.TestCase):
    def test_search_context_snapshots_accepts_offset(self):
        import inspect
        from service.context_snapshots import search_context_snapshots
        sig = inspect.signature(search_context_snapshots)
        self.assertIn("offset", sig.parameters,
                      "search_context_snapshots 应接受 offset 分页参数")

    def test_search_context_snapshots_offset_default_zero(self):
        import inspect
        from service.context_snapshots import search_context_snapshots
        sig = inspect.signature(search_context_snapshots)
        self.assertEqual(0, sig.parameters["offset"].default,
                         "search_context_snapshots offset 默认值应为 0")

    def test_search_recent_context_summaries_accepts_offset(self):
        import inspect
        from service.context_snapshots import search_recent_context_summaries
        sig = inspect.signature(search_recent_context_summaries)
        self.assertIn("offset", sig.parameters,
                      "search_recent_context_summaries 应接受 offset 分页参数")

    def test_search_recent_context_summaries_offset_default_zero(self):
        import inspect
        from service.context_snapshots import search_recent_context_summaries
        sig = inspect.signature(search_recent_context_summaries)
        self.assertEqual(0, sig.parameters["offset"].default,
                         "search_recent_context_summaries offset 默认值应为 0")


class SessionEventsLimitTests(unittest.TestCase):
    def test_context_events_limit_exists(self):
        from service.constants import CONTEXT_EVENTS_LIMIT
        self.assertIsInstance(CONTEXT_EVENTS_LIMIT, int,
                              "CONTEXT_EVENTS_LIMIT 应为 int 类型")

    def test_context_events_limit_positive(self):
        from service.constants import CONTEXT_EVENTS_LIMIT
        self.assertGreater(CONTEXT_EVENTS_LIMIT, 0,
                           "CONTEXT_EVENTS_LIMIT 应大于 0")


class CaptureCycleEvidenceBatchTests(unittest.TestCase):
    def test_run_capture_cycle_uses_batch_evidence(self):
        """run_capture_cycle 应使用 accumulate_evidence_batch，不应逐条调用 accumulate_evidence。"""
        import inspect
        from service import capture_cycle
        source = inspect.getsource(capture_cycle.run_capture_cycle)
        self.assertNotIn("accumulate_evidence(user_code",
                         source, "run_capture_cycle 不应再调用逐条的 accumulate_evidence")
        self.assertIn("accumulate_evidence_batch",
                      source, "run_capture_cycle 应使用 accumulate_evidence_batch")


class CaptureCycleBatchEmbeddingTests(unittest.TestCase):
    def test_run_capture_cycle_uses_batch_embedding_api(self):
        """run_capture_cycle 应使用 generate_embeddings_batch 而非逐条 refresh_memory_embedding。"""
        import inspect
        from service import capture_cycle
        source = inspect.getsource(capture_cycle.run_capture_cycle)
        self.assertIn("generate_embeddings_batch",
                      source,
                      "run_capture_cycle 应调用 generate_embeddings_batch 批量生成 embedding")


class RecentMemoryCacheTTLTests(unittest.TestCase):
    def test_recent_memory_ttl_is_at_least_300(self):
        """_RECENT_MEMORY_TTL 应 >= 300 秒以减少长对话重查。"""
        from service.analyzer import _RECENT_MEMORY_TTL
        self.assertGreaterEqual(_RECENT_MEMORY_TTL, 300,
                                "_RECENT_MEMORY_TTL 应至少 300 秒")

    def test_upsert_memory_clears_recent_memory_cache(self):
        """upsert_memory 写入后应清除 _recent_memory_cache，避免旧数据污染分析。"""
        import inspect
        from service import memory_ops
        source = inspect.getsource(memory_ops.upsert_memory)
        self.assertIn("_recent_memory_cache", source,
                      "upsert_memory 应在写入后清除 _recent_memory_cache")
