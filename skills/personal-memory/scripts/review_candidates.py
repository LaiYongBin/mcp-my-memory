#!/usr/bin/env python3
"""List pending review candidates."""

from __future__ import annotations

import argparse
import json
from urllib.error import HTTPError

from common import request_json, start_service
from service.memory_ops import list_review_candidates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-code")
    parser.add_argument("--limit", type=int, default=20)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = {"user_code": args.user_code, "limit": args.limit}
    if start_service():
        try:
            response = request_json("POST", "/memory/review/list", payload)
            print(json.dumps(response, ensure_ascii=False, default=str))
            return 0
        except HTTPError:
            pass
    rows = list_review_candidates(args.user_code, args.limit)
    print(json.dumps({"ok": True, "data": {"items": rows, "count": len(rows)}}, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
