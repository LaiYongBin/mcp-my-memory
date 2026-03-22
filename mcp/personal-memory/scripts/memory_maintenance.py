#!/usr/bin/env python3
"""Recalculate lifecycle and disclosure metadata for stored memories."""

from __future__ import annotations

import argparse
import json
from typing import Sequence

from service.memory_ops import maintain_memory_store


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-code")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-archived", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = maintain_memory_store(
        user_code=args.user_code,
        limit=args.limit,
        dry_run=args.dry_run,
        include_archived=args.include_archived,
    )
    print(json.dumps({"ok": True, "data": result}, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
