#!/usr/bin/env python3
"""Create or update personal memories."""

from __future__ import annotations

import argparse
import json

from common import request_json, start_service
from service.memory_ops import promote_memory, upsert_memory


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int)
    parser.add_argument("--user-code")
    parser.add_argument("--memory-type", default="fact")
    parser.add_argument("--title", required=False)
    parser.add_argument("--content", required=True)
    parser.add_argument("--summary")
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--source-type", default="manual")
    parser.add_argument("--source-ref")
    parser.add_argument("--confidence", type=float, default=0.7)
    parser.add_argument("--importance", type=int, default=5)
    parser.add_argument("--status", default="active")
    parser.add_argument("--explicit", action="store_true")
    parser.add_argument("--promote", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    title = args.title or args.content[:80]
    if args.promote:
        payload = {
            "text": args.content,
            "title": title,
            "user_code": args.user_code,
            "memory_type": args.memory_type,
            "tags": args.tag,
            "source_type": args.source_type,
            "source_ref": args.source_ref,
            "explicit": args.explicit,
        }
        if start_service():
            response = request_json("POST", "/memory/promote", payload)
            print(json.dumps(response, ensure_ascii=False, default=str))
            return 0
        row = promote_memory(payload)
        print(json.dumps({"ok": True, "data": row}, ensure_ascii=False, default=str))
        return 0

    payload = {
        "id": args.id,
        "user_code": args.user_code,
        "memory_type": args.memory_type,
        "title": title,
        "content": args.content,
        "summary": args.summary,
        "tags": args.tag,
        "source_type": args.source_type,
        "source_ref": args.source_ref,
        "confidence": args.confidence,
        "importance": args.importance,
        "status": args.status,
        "is_explicit": args.explicit,
    }
    if start_service():
        response = request_json("POST", "/memory/upsert", payload)
        print(json.dumps(response, ensure_ascii=False, default=str))
        return 0
    row = upsert_memory(payload)
    print(json.dumps({"ok": True, "data": row}, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
