#!/usr/bin/env python3
"""Sync a session transcript into segment/topic snapshots and optional memory extraction."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from service.context_snapshots import sync_session_context


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-key", default="default")
    parser.add_argument("--topic-hint")
    parser.add_argument("--source-ref")
    parser.add_argument("--user-code")
    parser.add_argument("--extract-memory", action="store_true")
    parser.add_argument("--turn", action="append", default=[], help="role:content")
    parser.add_argument("--transcript-file", help="JSON array of {role, content}")
    return parser.parse_args()


def load_turns(args: argparse.Namespace) -> list[dict]:
    turns = []
    if args.transcript_file:
        turns.extend(json.loads(Path(args.transcript_file).read_text(encoding="utf-8")))
    for raw in args.turn:
        role, _, content = raw.partition(":")
        if role and content:
            turns.append({"role": role.strip(), "content": content.strip()})
    return turns


def main() -> int:
    args = parse_args()
    request_timeout = int(os.environ.get("LYB_SKILL_MEMORY_CONTEXT_SYNC_TIMEOUT", "180"))
    payload = {
        "session_key": args.session_key,
        "turns": load_turns(args),
        "user_code": args.user_code,
        "topic_hint": args.topic_hint,
        "source_ref": args.source_ref,
        "extract_memory": args.extract_memory,
    }
    result = sync_session_context(**payload)
    print(json.dumps({"ok": True, "data": result}, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
