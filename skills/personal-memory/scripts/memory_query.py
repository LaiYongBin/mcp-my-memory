#!/usr/bin/env python3
"""Search personal memories, preferring the service and falling back to direct PG access."""

from __future__ import annotations

import argparse
import json

from common import request_json, start_service
from service.memory_ops import search_memories


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="")
    parser.add_argument("--user-code")
    parser.add_argument("--memory-type")
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--include-archived", action="store_true")
    parser.add_argument("--limit", type=int, default=10)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = {
        "query": args.query,
        "user_code": args.user_code,
        "memory_type": args.memory_type,
        "tags": args.tag,
        "include_archived": args.include_archived,
        "limit": args.limit,
    }
    if start_service():
        response = request_json("POST", "/memory/search", payload)
        print(json.dumps(response, ensure_ascii=False, default=str))
        return 0
    rows = search_memories(
        query=args.query,
        user_code=args.user_code,
        memory_type=args.memory_type,
        tags=args.tag,
        include_archived=args.include_archived,
        limit=args.limit,
    )
    print(json.dumps({"ok": True, "data": {"items": rows, "count": len(rows)}}, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
