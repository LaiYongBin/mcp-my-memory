#!/usr/bin/env python3
"""Search stored session context snapshots."""

from __future__ import annotations

import argparse
import json

from service.context_snapshots import search_context_snapshots


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="")
    parser.add_argument("--session-key")
    parser.add_argument("--snapshot-level")
    parser.add_argument("--user-code")
    parser.add_argument("--limit", type=int, default=10)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = {
        "query": args.query,
        "session_key": args.session_key,
        "snapshot_level": args.snapshot_level,
        "user_code": args.user_code,
        "limit": args.limit,
    }
    result = search_context_snapshots(**payload)
    print(json.dumps({"ok": True, "data": {"items": result, "count": len(result)}}, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
