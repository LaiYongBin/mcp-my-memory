#!/usr/bin/env python3
"""Search personal memories, preferring the service and falling back to direct PG access."""

from __future__ import annotations

import argparse
import json

from service.memory_ops import search_memories


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="")
    parser.add_argument("--user-code")
    parser.add_argument("--memory-type")
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--include-archived", action="store_true")
    parser.add_argument("--min-importance", type=int)
    parser.add_argument("--min-confidence", type=float)
    parser.add_argument("--explicit", action="store_true")
    parser.add_argument("--created-after")
    parser.add_argument("--created-before")
    parser.add_argument("--updated-after")
    parser.add_argument("--updated-before")
    parser.add_argument("--valid-at")
    parser.add_argument("--limit", type=int, default=10)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = search_memories(
        query=args.query,
        user_code=args.user_code,
        memory_type=args.memory_type,
        tags=args.tag,
        include_archived=args.include_archived,
        min_importance=args.min_importance,
        min_confidence=args.min_confidence,
        is_explicit=True if args.explicit else None,
        created_after=args.created_after,
        created_before=args.created_before,
        updated_after=args.updated_after,
        updated_before=args.updated_before,
        valid_at=args.valid_at,
        limit=args.limit,
    )
    print(json.dumps({"ok": True, "data": {"items": rows, "count": len(rows)}}, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
