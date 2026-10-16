#!/usr/bin/env python3
"""Start the API on a free port, wait for /api/health, run a command with $BASE_URL set, stop the server.

Usage: PYTHONPATH=api uv run python scripts/with_server.py -- scripts/smoke.sh
The command receives the base URL as its last argument and in $BASE_URL. Exit code is the command's.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def wait_health(base: str, timeout_s: float = 30.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base}/api/health", timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.3)
    return False


def main(argv: list[str]) -> int:
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    if not argv:
        print(__doc__)
        return 2
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "api"),
        "TWILIO_VALIDATE": os.environ.get("TWILIO_VALIDATE", "0"),
    }
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "reach.app:create_app",
            "--factory",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=ROOT,
        env=env,
    )
    try:
        if not wait_health(base):
            print("server did not become healthy", file=sys.stderr)
            return 1
        cmd = [sys.executable, *argv] if argv[0].endswith(".py") else list(argv)
        result = subprocess.run([*cmd, base], cwd=ROOT, env={**env, "BASE_URL": base}, check=False)
        return result.returncode
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
