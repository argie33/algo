#!/usr/bin/env python3
"""Fast dev startup - skip data pipelines, start API + React dev server only.

Usage:
    python start_dev_fast.py              # Start dev_server on 3001 + React on 5173
"""

import os
import subprocess
import sys
import time
from pathlib import Path

os.environ["LOCAL_MODE"] = "true"
os.environ["ENVIRONMENT"] = "development"
os.environ["ALPACA_PAPER_TRADING"] = "true"

repo_root = Path(__file__).parent
log_dir = repo_root / ".algo" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)

def start_dev_server(port: int = 3001) -> subprocess.Popen:
    """Start dev_server in background."""
    print(f"[DEV] Starting API dev_server on http://127.0.0.1:{port}...")

    dev_server_path = repo_root / "lambda" / "api" / "dev_server.py"
    log_file = log_dir / "dev_server.log"

    env = os.environ.copy()
    env["LOCAL_MODE"] = "true"
    env["ENVIRONMENT"] = "development"

    with open(log_file, "a") as f:
        f.write(f"\n{'='*60}\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting dev_server\n{'='*60}\n")

    log_handle = open(log_file, "a")

    process = subprocess.Popen(
        [sys.executable, str(dev_server_path)],
        cwd=str(repo_root),
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    # Wait for server to start
    for i in range(30):
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex(("127.0.0.1", port))
            sock.close()
            if result == 0:
                print(f"[DEV] ✓ API dev_server running on 127.0.0.1:{port}")
                print(f"[DEV] Log: {log_file}")
                return process
        except:
            pass
        time.sleep(0.5)

    print(f"[DEV] ✗ Dev server failed to start within 15s")
    process.terminate()
    return process


def start_react_server() -> subprocess.Popen | None:
    """Start React dev server (Vite)."""
    try:
        react_dir = repo_root / "webapp" / "frontend"
        if not react_dir.exists():
            print(f"[DEV] React directory not found: {react_dir}")
            return None

        print("[DEV] Starting React dev server on http://127.0.0.1:5173...")

        process = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=str(react_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        # Give it a few seconds to start
        time.sleep(3)
        if process.poll() is None:
            print("[DEV] ✓ React dev server started")
            return process
        else:
            print("[DEV] ✗ React dev server failed to start")
            return None

    except FileNotFoundError:
        print("[DEV] npm not found - skipping React dev server")
        return None
    except Exception as e:
        print(f"[DEV] React start error: {e}")
        return None


def main():
    """Start dev servers and wait for user interrupt."""
    print("[DEV] ============================================================")
    print("[DEV] FAST DEV STARTUP (skipping data pipelines)")
    print("[DEV] ============================================================")
    print()

    try:
        dev_process = start_dev_server()
        react_process = start_react_server()

        print()
        print("[DEV] ============================================================")
        print("[DEV] Dev servers running:")
        print("[DEV]   API:   http://127.0.0.1:3001")
        print("[DEV]   React: http://127.0.0.1:5173")
        print("[DEV]")
        print("[DEV] Press Ctrl+C to stop")
        print("[DEV] ============================================================")
        print()

        # Wait for interrupt
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n[DEV] Shutting down...")

        if react_process:
            react_process.terminate()
            try:
                react_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                react_process.kill()

        if dev_process:
            dev_process.terminate()
            try:
                dev_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                dev_process.kill()

        print("[DEV] Stopped")
        return 0

    except Exception as e:
        print(f"\n[DEV] Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
