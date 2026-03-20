#!/usr/bin/env python3
"""Backfill embeddings for existing memories when embedding env vars are configured."""

from __future__ import annotations

import json

from service.db import get_conn
from service.embeddings import embeddings_enabled, refresh_memory_embedding


def main() -> int:
    if not embeddings_enabled():
        print(json.dumps({"ok": False, "message": "embedding env vars not configured"}))
        return 1

    count = 0
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, user_code, coalesce(summary, content, title) AS embed_text
            FROM memory_item
            WHERE deleted_at IS NULL
            ORDER BY id ASC
            """
        )
        rows = cur.fetchall()

    for row in rows:
        embed_text = (row["embed_text"] or "").strip()
        if not embed_text:
            continue
        if refresh_memory_embedding(int(row["id"]), row["user_code"], embed_text):
            count += 1

    print(json.dumps({"ok": True, "embedded": count}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
