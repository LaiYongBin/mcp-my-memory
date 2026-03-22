#!/usr/bin/env python3
"""Approve or reject pending review candidates."""

from __future__ import annotations

import argparse
import json

from service.memory_ops import approve_review_candidate, reject_review_candidate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, required=True)
    parser.add_argument("--user-code")
    parser.add_argument("--action", choices=["approve", "reject"], required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.action == "approve":
        result = approve_review_candidate(args.id, args.user_code)
    else:
        result = reject_review_candidate(args.id, args.user_code)
    print(json.dumps({"ok": bool(result), "data": result}, ensure_ascii=False, default=str))
    return 0 if result else 1


if __name__ == "__main__":
    raise SystemExit(main())
