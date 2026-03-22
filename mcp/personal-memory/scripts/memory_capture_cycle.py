#!/usr/bin/env python3
"""Capture one conversation turn into long-term, working, or review memory."""

from __future__ import annotations

import argparse
import json

from service.capture_cycle import run_capture_cycle


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-text", required=True)
    parser.add_argument("--assistant-text", default="")
    parser.add_argument("--session-key", default="default")
    parser.add_argument("--source-ref")
    parser.add_argument("--user-code")
    parser.add_argument("--no-consolidate", action="store_true")
    parser.add_argument("--async-mode", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = {
        "user_text": args.user_text,
        "assistant_text": args.assistant_text,
        "session_key": args.session_key,
        "source_ref": args.source_ref,
        "user_code": args.user_code,
        "consolidate": not args.no_consolidate,
    }
    result = run_capture_cycle(**payload)
    output = {"ok": True, "data": result}
    if args.async_mode:
        output["message"] = "CLI mode runs synchronously; use the MCP tool from a client for integrated workflows."
    print(json.dumps(output, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
