"""Optional embedding generation and vector search helpers."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen

from pgvector.psycopg import Vector

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
    with urlopen(request, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))
    if "data" in data:
        return data["data"][0]["embedding"]
    return data["output"]["embeddings"][0]["embedding"]


def refresh_memory_embedding(memory_id: int, user_code: str, chunk_text: str) -> bool:
    embedding = generate_embedding(chunk_text)
    if not embedding:
        return False
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM memory_embedding
            WHERE memory_id = %s AND user_code = %s
            """,
            (memory_id, user_code),
        )
        cur.execute(
            """
            INSERT INTO memory_embedding (
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
            FROM memory_embedding me
            JOIN memory_item mi ON mi.id = me.memory_id
            WHERE me.user_code = %s
              AND mi.deleted_at IS NULL
              AND mi.status = 'active'
            ORDER BY me.embedding <=> %s
            LIMIT %s
            """,
            (Vector(embedding), user_code, Vector(embedding), limit),
        )
        rows = cur.fetchall()
    return [dict(row) for row in rows]
