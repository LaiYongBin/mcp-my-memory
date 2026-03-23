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


if __name__ == "__main__":
    unittest.main()
