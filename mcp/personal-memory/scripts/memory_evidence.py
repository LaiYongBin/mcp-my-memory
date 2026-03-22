#!/usr/bin/env python3
"""List accumulated memory evidence for debugging and review."""

from __future__ import annotations

import argparse
import json

from service.evidence import list_evidence


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-code")
    parser.add_argument("--conflict-scope")
    parser.add_argument("--limit", type=int, default=20)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    items = list_evidence(
        user_code=args.user_code,
        conflict_scope=args.conflict_scope,
        limit=args.limit,
    )
    print(json.dumps({"ok": True, "data": {"items": items, "count": len(items)}}, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
