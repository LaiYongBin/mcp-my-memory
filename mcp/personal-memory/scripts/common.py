"""Shared helpers for scripts."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_FILE = Path("/tmp/my_skillproject-memory-service.log")


def service_url(path: str = "") -> str:
    host = os.environ.get("LYB_SKILL_MEMORY_SERVICE_HOST", "127.0.0.1")
    port = os.environ.get("LYB_SKILL_MEMORY_SERVICE_PORT", "8787")
    mount_path = os.environ.get("LYB_SKILL_MEMORY_MCP_PATH", "/mcp")
    suffix = path or mount_path
    return f"http://{host}:{port}{suffix}"


def is_service_healthy(timeout: int = 2) -> bool:
    try:
        with socket.create_connection(
            (
                os.environ.get("LYB_SKILL_MEMORY_SERVICE_HOST", "127.0.0.1"),
                int(os.environ.get("LYB_SKILL_MEMORY_SERVICE_PORT", "8787")),
            ),
            timeout=timeout,
        ):
            return True
    except (TimeoutError, ConnectionError, OSError):
        return False


def start_service() -> bool:
    if is_service_healthy():
        return True
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("ab") as log_file:
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "service.mcp_server",
                "--transport",
                "streamable-http",
                "--host",
                os.environ.get("LYB_SKILL_MEMORY_SERVICE_HOST", "127.0.0.1"),
                "--port",
                os.environ.get("LYB_SKILL_MEMORY_SERVICE_PORT", "8787"),
                "--path",
                os.environ.get("LYB_SKILL_MEMORY_MCP_PATH", "/mcp"),
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
