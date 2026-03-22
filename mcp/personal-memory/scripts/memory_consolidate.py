#!/usr/bin/env python3
"""Consolidate and expire working memories."""

from __future__ import annotations

import argparse
import json

from service.capture_cycle import consolidate_working_memories, list_working_memories


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-code")
    parser.add_argument("--session-key")
    parser.add_argument("--list-only", action="store_true")
    parser.add_argument("--limit", type=int, default=20)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.list_only:
        rows = list_working_memories(user_code=args.user_code, session_key=args.session_key, limit=args.limit)
        print(json.dumps({"ok": True, "data": {"items": rows, "count": len(rows)}}, ensure_ascii=False, default=str))
        return 0

    result = consolidate_working_memories(user_code=args.user_code, session_key=args.session_key)
    print(json.dumps({"ok": True, "data": result}, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
