#!/usr/bin/env python3
"""Approve or reject pending review candidates."""

from __future__ import annotations

import argparse
import json
from urllib.error import HTTPError

from common import request_json, start_service
from service.memory_ops import approve_review_candidate, reject_review_candidate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, required=True)
    parser.add_argument("--user-code")
    parser.add_argument("--action", choices=["approve", "reject"], required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = {"id": args.id, "user_code": args.user_code, "action": args.action}
    if start_service():
        try:
            response = request_json("POST", "/memory/review/action", payload, timeout=30)
            print(json.dumps(response, ensure_ascii=False, default=str))
            return 0
        except HTTPError:
            pass

    if args.action == "approve":
        result = approve_review_candidate(args.id, args.user_code)
    else:
        result = reject_review_candidate(args.id, args.user_code)
    print(json.dumps({"ok": bool(result), "data": result}, ensure_ascii=False, default=str))
    return 0 if result else 1


if __name__ == "__main__":
    raise SystemExit(main())
