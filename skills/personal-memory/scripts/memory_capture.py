#!/usr/bin/env python3
"""Extract and optionally persist candidate memories from user text."""

from __future__ import annotations

import argparse
import json

from common import request_json, start_service
from service.db import get_settings
from service.extraction import extract_candidates, extract_review_candidates, should_auto_persist
from service.memory_ops import save_review_candidate, upsert_memory


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--user-code")
    parser.add_argument("--auto-persist", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = {
        "text": args.text,
        "user_code": args.user_code,
        "auto_persist": args.auto_persist,
    }
    if start_service():
        response = request_json("POST", "/memory/capture", payload)
        print(json.dumps(response, ensure_ascii=False, default=str))
        return 0

    candidates = extract_candidates(args.text)
    review_candidates = extract_review_candidates(args.text)
    persisted = []
    remaining = []
    review_items = []
    for candidate in candidates:
        auto_persist = args.auto_persist or should_auto_persist(candidate)
        if auto_persist:
            candidate["user_code"] = args.user_code
            persisted.append(upsert_memory(candidate))
        else:
            remaining.append(candidate)
    resolved_user = args.user_code or str(get_settings()["memory_user"])
    for candidate in review_candidates:
        review_items.append(
            save_review_candidate(user_code=resolved_user, source_text=args.text, candidate=candidate)
        )
    print(
        json.dumps(
            {
                "ok": True,
                "data": {
                    "persisted": persisted,
                    "persisted_count": len(persisted),
                    "candidates": remaining,
                    "candidate_count": len(remaining),
                    "review_candidates": review_items,
                    "review_candidate_count": len(review_items),
                },
            },
            ensure_ascii=False,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
