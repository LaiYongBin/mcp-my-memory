#!/usr/bin/env python3
"""Archive or logically delete personal memories."""

from __future__ import annotations

import argparse
import json

from common import request_json, start_service
from service.memory_ops import archive_memory, delete_memory


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, required=True)
    parser.add_argument("--user-code")
    parser.add_argument("--archive", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = {"id": args.id, "user_code": args.user_code}
    if args.archive:
        if start_service():
            response = request_json("POST", "/memory/archive", payload)
            print(json.dumps(response, ensure_ascii=False, default=str))
            return 0
        row = archive_memory(args.id, args.user_code)
    else:
        if start_service():
            response = request_json("POST", "/memory/delete", payload)
            print(json.dumps(response, ensure_ascii=False, default=str))
            return 0
        row = delete_memory(args.id, args.user_code)
    print(json.dumps({"ok": bool(row), "data": row}, ensure_ascii=False, default=str))
    return 0 if row else 1


if __name__ == "__main__":
    raise SystemExit(main())
