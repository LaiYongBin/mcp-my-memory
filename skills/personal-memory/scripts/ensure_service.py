#!/usr/bin/env python3
"""Check and start the personal memory service if needed."""

from __future__ import annotations

import json
import sys

from common import is_service_healthy, service_url, start_service


def main() -> int:
    if is_service_healthy():
        print(json.dumps({"ok": True, "started": False, "url": service_url()}))
        return 0
    started = start_service()
    print(json.dumps({"ok": started, "started": started, "url": service_url()}))
    return 0 if started else 1


if __name__ == "__main__":
    raise SystemExit(main())
