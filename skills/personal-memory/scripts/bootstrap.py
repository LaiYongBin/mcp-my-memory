#!/usr/bin/env python3
"""Bootstrap the personal-memory skill on a new machine."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


SQL_FILES = [
    "001_schema.sql",
    "002_indexes.sql",
    "003_pgvector_upgrade.sql",
    "004_review_candidates.sql",
    "005_capture_cycle.sql",
    "006_memory_analysis.sql",
    "007_slot_memory.sql",
    "008_evidence_accumulation.sql",
    "009_context_snapshots.sql",
]

REQUIRED_ENV_VARS = [
    "LYB_SKILL_PG_ADDRESS",
    "LYB_SKILL_PG_USERNAME",
    "LYB_SKILL_PG_PASSWORD",
    "LYB_SKILL_PG_MY_PERSONAL_DATABASE",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-db", action="store_true")
    parser.add_argument("--skip-service", action="store_true")
    parser.add_argument("--backfill-embeddings", action="store_true")
    parser.add_argument("--print-env-template", action="store_true")
    return parser.parse_args()


def check_env() -> List[str]:
    return [name for name in REQUIRED_ENV_VARS if not os.environ.get(name)]


def env_template() -> str:
    return """export LYB_SKILL_PG_ADDRESS=
export LYB_SKILL_PG_PORT=5432
export LYB_SKILL_PG_USERNAME=
export LYB_SKILL_PG_PASSWORD=
export LYB_SKILL_PG_MY_PERSONAL_DATABASE=
export LYB_SKILL_MEMORY_USER=LYB

export LYB_SKILL_MEMORY_SERVICE_HOST=127.0.0.1
export LYB_SKILL_MEMORY_SERVICE_PORT=8787

export LYB_SKILL_MEMORY_EMBED_API_KEY=
export LYB_SKILL_MEMORY_EMBED_BASE_URL=https://dashscope.aliyuncs.com/api/v1
export LYB_SKILL_MEMORY_EMBED_MODEL=text-embedding-v4
export LYB_SKILL_MEMORY_EMBED_DIM=1536
"""


def apply_sql_file(name: str) -> None:
    from service.db import get_conn

    sql_path = ROOT / "sql" / name
    sql = sql_path.read_text(encoding="utf-8")
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql)
        conn.commit()


def ensure_database() -> List[Tuple[str, str]]:
    results = []
    for name in SQL_FILES:
        apply_sql_file(name)
        results.append((name, "applied"))
    return results


def verify_database() -> dict:
    from service.db import get_conn

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT extname
            FROM pg_extension
            WHERE extname = 'vector'
            """
        )
        vector_extension = cur.fetchone() is not None
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name IN (
                  'memory_item',
                  'memory_embedding',
                  'working_memory',
                  'memory_review_candidate',
                  'conversation_event',
                  'memory_analysis_result',
                  'memory_evidence',
                  'conversation_context_snapshot'
              )
            ORDER BY table_name
            """
        )
        tables = [row["table_name"] for row in cur.fetchall()]
    return {
        "vector_extension": vector_extension,
        "tables": tables,
    }


def maybe_backfill_embeddings() -> dict:
    from scripts.embed_backfill import backfill_embeddings

    return backfill_embeddings(limit=200)


def main() -> int:
    args = parse_args()
    if args.print_env_template:
        print(env_template())
        return 0

    from scripts.common import is_service_healthy, request_json, start_service
    from service.db import get_settings

    missing_env = check_env()
    if missing_env:
        print(
            json.dumps(
                {
                    "ok": False,
                    "missing_env": missing_env,
                    "hint": "Run with --print-env-template to see the expected environment variables.",
                },
                ensure_ascii=False,
            )
        )
        return 1

    output = {
        "ok": True,
        "settings": get_settings(),
        "db": None,
        "service": None,
        "embeddings": None,
    }

    if not args.skip_db:
        output["db"] = {
            "sql": ensure_database(),
            "verify": verify_database(),
        }

    if args.backfill_embeddings:
        output["embeddings"] = maybe_backfill_embeddings()

    if not args.skip_service:
        started = start_service()
        service_health = is_service_healthy()
        service_payload = {}
        if service_health:
            try:
                service_payload = request_json("GET", "/health")
            except Exception:
                service_payload = {}
        output["service"] = {
            "started": started,
            "healthy": service_health,
            "health": service_payload,
        }

    print(json.dumps(output, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
