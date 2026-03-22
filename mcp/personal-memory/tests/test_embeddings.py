from __future__ import annotations

import ssl
import unittest
from urllib.error import URLError
from unittest.mock import MagicMock, patch


class EmbeddingHelpersTests(unittest.TestCase):
    @patch("service.embeddings.os.path.exists")
    @patch("service.embeddings.certifi.where")
    def test_resolve_ssl_cafile_prefers_certifi_bundle(
        self, certifi_where_mock, exists_mock
    ) -> None:
        from service.embeddings import resolve_ssl_cafile

        certifi_where_mock.return_value = "/tmp/certifi.pem"
        exists_mock.side_effect = lambda path: path == "/tmp/certifi.pem"

        self.assertEqual("/tmp/certifi.pem", resolve_ssl_cafile())

    @patch("service.embeddings.urlopen")
    @patch("service.embeddings.embedding_config")
    def test_generate_embedding_returns_none_on_tls_failure(
        self, embedding_config_mock, urlopen_mock
    ) -> None:
        from service.embeddings import generate_embedding

        embedding_config_mock.return_value = {
            "api_key": "test-key",
            "base_url": "https://dashscope.aliyuncs.com/api/v1",
            "model": "text-embedding-v4",
            "dimension": 1536,
        }
        urlopen_mock.side_effect = URLError(
            ssl.SSLCertVerificationError("unable to get local issuer certificate")
        )

        self.assertIsNone(generate_embedding("最喜欢的运动"))


class MemorySearchFallbackTests(unittest.TestCase):
    @patch("service.memory_ops.vector_search")
    @patch("service.memory_ops.embeddings_enabled", return_value=True)
    @patch("service.memory_ops.get_settings", return_value={"memory_user": "LYB"})
    @patch("service.memory_ops.get_conn")
    def test_search_memories_falls_back_when_vector_search_fails(
        self,
        get_conn_mock,
        _get_settings_mock,
        _embeddings_enabled_mock,
        vector_search_mock,
    ) -> None:
        from service.memory_ops import search_memories

        vector_search_mock.side_effect = URLError(
            ssl.SSLCertVerificationError("unable to get local issuer certificate")
        )

        row = {
            "id": 17,
            "user_code": "LYB",
            "memory_type": "preference",
            "title": "favorite_sport: 自行车",
            "content": "用户最喜欢的运动是自行车。",
            "summary": None,
            "tags": [],
            "source_type": "manual",
            "source_ref": None,
            "confidence": 0.95,
            "importance": 5,
            "status": "active",
            "is_explicit": True,
            "supersedes_id": None,
            "conflict_with_id": None,
            "valid_from": None,
            "valid_to": None,
            "subject_key": "user",
            "attribute_key": "favorite_sport",
            "value_text": "自行车",
            "conflict_scope": None,
            "created_at": "2026-03-20T16:11:46+08:00",
            "updated_at": "2026-03-20T16:11:46+08:00",
            "deleted_at": None,
            "rank_score": 0.9,
        }

        cursor = MagicMock()
        cursor.fetchall.return_value = [row]
        conn = MagicMock()
        conn.__enter__.return_value = conn
        conn.cursor.return_value.__enter__.return_value = cursor
        get_conn_mock.return_value = conn

        results = search_memories(query="最喜欢的运动", limit=5)

        self.assertEqual(1, len(results))
        self.assertEqual(17, results[0]["id"])
        self.assertEqual(0.0, results[0]["vector_score"])
        self.assertGreater(results[0]["hybrid_score"], 0.0)


if __name__ == "__main__":
    unittest.main()
