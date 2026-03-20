"""Shared helpers for scripts."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_FILE = Path("/tmp/my_skillproject-memory-service.log")


def service_url(path: str = "") -> str:
    host = os.environ.get("LYB_SKILL_MEMORY_SERVICE_HOST", "127.0.0.1")
    port = os.environ.get("LYB_SKILL_MEMORY_SERVICE_PORT", "8787")
    return f"http://{host}:{port}{path}"


def request_json(
    method: str, path: str, payload: Optional[Dict] = None, timeout: int = 5
) -> Dict:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(service_url(path), data=data, headers=headers, method=method)
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def is_service_healthy(timeout: int = 2) -> bool:
    try:
        payload = request_json("GET", "/health", timeout=timeout)
    except (URLError, TimeoutError, ConnectionError, OSError):
        return False
    return bool(payload.get("ok"))


def start_service() -> bool:
    if is_service_healthy():
        return True
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("ab") as log_file:
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "service.app:app",
                "--host",
                os.environ.get("LYB_SKILL_MEMORY_SERVICE_HOST", "127.0.0.1"),
                "--port",
                os.environ.get("LYB_SKILL_MEMORY_SERVICE_PORT", "8787"),
            ],
            cwd=PROJECT_ROOT,
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
        )
    for _ in range(15):
        if is_service_healthy():
            return True
        time.sleep(1)
    return False
