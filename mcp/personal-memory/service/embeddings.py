"""Optional embedding generation and vector search helpers."""

from __future__ import annotations

import json
import os
import ssl
from typing import Any, Dict, List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

import certifi

from pgvector.psycopg import Vector

from service.constants import STATUS_ACTIVE
from service.db import get_conn


def embedding_config() -> Dict[str, Any]:
    return {
        "api_key": os.environ.get("LYB_SKILL_MEMORY_EMBED_API_KEY"),
        "base_url": os.environ.get(
            "LYB_SKILL_MEMORY_EMBED_BASE_URL", "https://dashscope.aliyuncs.com/api/v1"
        ),
        "model": os.environ.get("LYB_SKILL_MEMORY_EMBED_MODEL", "text-embedding-3-small"),
        "dimension": int(os.environ.get("LYB_SKILL_MEMORY_EMBED_DIM", "1536")),
    }


def embeddings_enabled() -> bool:
    config = embedding_config()
    return bool(config["api_key"] and config["model"])


def resolve_ssl_cafile() -> Optional[str]:
    candidates = [
        os.environ.get("SSL_CERT_FILE"),
        certifi.where(),
        "/private/etc/ssl/cert.pem",
        "/etc/ssl/cert.pem",
        "/etc/ssl/certs/ca-certificates.crt",
        "/etc/pki/tls/certs/ca-bundle.crt",
        "/usr/local/etc/openssl@3/cert.pem",
        "/opt/homebrew/etc/openssl@3/cert.pem",
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def build_ssl_context() -> ssl.SSLContext:
    cafile = resolve_ssl_cafile()
    if cafile:
        return ssl.create_default_context(cafile=cafile)
    return ssl.create_default_context()


# 模块级 SSL context 缓存，避免每次 generate_embedding 重复创建
_ssl_context_cache: Optional["ssl.SSLContext"] = None


def _get_ssl_context() -> "ssl.SSLContext":
    global _ssl_context_cache
    if _ssl_context_cache is None:
        _ssl_context_cache = build_ssl_context()
    return _ssl_context_cache


def generate_embedding(text: str) -> Optional[List[float]]:
    if not embeddings_enabled():
        return None
    config = embedding_config()
    base_url = str(config["base_url"]).rstrip("/")
    if base_url.endswith("/api/v1"):
        url = base_url + "/services/embeddings/text-embedding/text-embedding"
        payload = {
            "model": config["model"],
            "input": {"texts": [text]},
            "parameters": {
                "dimension": config["dimension"],
                "output_type": "dense",
            },
        }
    else:
        url = base_url + "/embeddings"
        payload = {
            "model": config["model"],
            "input": text,
            "dimensions": config["dimension"],
            "encoding_format": "float",
        }
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + str(config["api_key"]),
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=20, context=_get_ssl_context()) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        return None
    if "data" in data:
        return data["data"][0]["embedding"]
    return data["output"]["embeddings"][0]["embedding"]


def generate_embeddings_batch(texts: List[str]) -> List[Optional[List[float]]]:
    """批量生成 embedding，减少 HTTP 请求次数。返回与 texts 等长的列表，失败项为 None。"""
    if not texts:
        return []
    if not embeddings_enabled():
        return [None] * len(texts)
    config = embedding_config()
    base_url = str(config["base_url"]).rstrip("/")
    if base_url.endswith("/api/v1"):
        # DashScope 原生 API：支持 texts 批量传入
        url = base_url + "/services/embeddings/text-embedding/text-embedding"
        payload = {
            "model": config["model"],
            "input": {"texts": texts},
            "parameters": {
                "dimension": config["dimension"],
                "output_type": "dense",
            },
        }
    else:
        # OpenAI 兼容 API：input 直接传 list
        url = base_url + "/embeddings"
        payload = {
            "model": config["model"],
            "input": texts,
            "dimensions": config["dimension"],
            "encoding_format": "float",
        }
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + str(config["api_key"]),
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30, context=_get_ssl_context()) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        return [None] * len(texts)
    try:
        if "data" in data:
            embeddings = data["data"]
            return [item["embedding"] for item in embeddings]
        embeddings = data["output"]["embeddings"]
        return [item["embedding"] for item in embeddings]
    except (KeyError, IndexError, TypeError):
        return [None] * len(texts)


def refresh_memory_embedding(memory_id: int, user_code: str, chunk_text: str) -> bool:
    embedding = generate_embedding(chunk_text)
    if not embedding:
        return False
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM memory_vector_chunk
            WHERE memory_id = %s AND user_code = %s
            """,
            (memory_id, user_code),
        )
        cur.execute(
            """
            INSERT INTO memory_vector_chunk (
                memory_id, user_code, chunk_index, chunk_text, embedding_text_hash, embedding
            ) VALUES (%s, %s, 0, %s, md5(%s), %s)
            """,
            (memory_id, user_code, chunk_text, chunk_text, Vector(embedding)),
        )
        conn.commit()
    return True


def vector_search(query: str, user_code: str, limit: int = 10) -> List[Dict[str, Any]]:
    embedding = generate_embedding(query)
    if not embedding:
        return []
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT me.memory_id,
                   1 - (me.embedding <=> %s) AS vector_score
            FROM memory_vector_chunk me
            JOIN memory_record mi ON mi.id = me.memory_id
            WHERE me.user_code = %s
              AND mi.deleted_at IS NULL
              AND mi.status = %s
            ORDER BY me.embedding <=> %s
            LIMIT %s
            """,
            (Vector(embedding), user_code, STATUS_ACTIVE, Vector(embedding), limit),
        )
        rows = cur.fetchall()
    return [dict(row) for row in rows]
