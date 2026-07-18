#!/usr/bin/env python3
"""Unified dashboard startup script for local development.

Starts loaders → dev_server in background (if needed) → dashboard.
This eliminates stale data by automatically loading fresh prices/indicators.

Usage:
    python start_dashboard_dev.py              # Start with auto-refresh disabled
    python start_dashboard_dev.py -w 30        # Start with auto-refresh every 30s
    python start_dashboard_dev.py --help       # Show all options
"""

import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path


def is_port_open(port: int, timeout: float = 1.0) -> bool:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex(("127.0.0.1", port))
        sock.close()
        return result == 0
    except Exception:
        return False


def cleanup_orphaned_dev_servers() -> None:
    """Kill any stuck/orphaned dev_server processes to prevent port conflicts."""
    try:
        if sys.platform == "win32":
            # Windows: use taskkill to kill only dev_server processes
            result = subprocess.run(
                ["tasklist", "/FI", "WINDOWTITLE eq dev_server*", "/FO", "CSV"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            # Alternative: Use wmic to find python processes running dev_server.py
            subprocess.run(
                'wmic process where "CommandLine like \'%dev_server%\'" delete /nointeractive 2>nul',
                shell=True,
                capture_output=True,
                timeout=5,
            )
        else:
            # Unix: use pkill to force-kill dev_server processes only
            subprocess.run(
                ["pkill", "-9", "-f", "dev_server.py"],
                capture_output=True,
                timeout=5,
            )
        time.sleep(1)  # Give port time to be released
    except Exception:
        # Silently fail - not critical if cleanup doesn't work
        pass


def run_morning_loaders() -> bool:
    """Run morning data loaders to ensure fresh prices/indicators.

    Returns True if successful, False if loaders failed/timed out.
    Non-critical: dashboard will still start even if loaders fail, just with stale data.
    """
    print("[STARTUP] Loading fresh data (prices, technical indicators, market status)...", flush=True)

    repo_root = Path(__file__).parent
    loaders_to_run = [
        "load_prices.py",
        "load_technical_indicators.py",
        "load_market_status_daily.py",
        "load_short_interest_finra.py",
        "load_price_extremes.py",
    ]

    success_count = 0
    for loader_name in loaders_to_run:
        loader_path = repo_root / "loaders" / loader_name
        if not loader_path.exists():
            print(f"[STARTUP] [SKIP] Loader not found: {loader_name}", flush=True)
            continue

        try:
            env = os.environ.copy()
            env["LOCAL_MODE"] = "1"
            result = subprocess.run(
                [sys.executable, str(loader_path)],
                cwd=str(repo_root),
                env=env,
                timeout=120,  # 2 min per loader
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                print(f"[STARTUP] [OK] {loader_name}", flush=True)
                success_count += 1
            else:
                print(f"[STARTUP] [WARN] {loader_name} returned code {result.returncode}", flush=True)
                if "error" in result.stderr.lower():
                    print(f"[STARTUP]       Error: {result.stderr[:100]}", flush=True)
        except subprocess.TimeoutExpired:
            print(f"[STARTUP] [WARN] {loader_name} timed out (2m)", flush=True)
        except Exception as e:
            print(f"[STARTUP] [WARN] {loader_name} error: {e}", flush=True)

    if success_count > 0:
        print(f"[STARTUP] [OK] Loaded fresh data ({success_count}/{len(loaders_to_run)} loaders)", flush=True)
        return True
    else:
        print(f"[STARTUP] [WARN] No loaders succeeded (dashboard will show stale data)", flush=True)
        return False


def start_dev_server() -> subprocess.Popen:
    """Start dev_server in background and wait for it to be ready."""
    print("[STARTUP] Checking if dev_server (localhost:3001) is already running...", flush=True)

    # Check if already running
    if is_port_open(3001):
        print("[STARTUP] [OK] Dev server already running on localhost:3001", flush=True)
        return None

    # Clean up any orphaned dev_server processes before starting fresh
    print("[STARTUP] Cleaning up any orphaned processes...", flush=True)
    cleanup_orphaned_dev_servers()

    print("[STARTUP] Dev server not responding. Starting it now...", flush=True)
    print("[STARTUP]   Running: python3 lambda/api/dev_server.py", flush=True)

    repo_root = Path(__file__).parent
    dev_server_path = repo_root / "lambda" / "api" / "dev_server.py"

    if not dev_server_path.exists():
        raise FileNotFoundError(f"dev_server.py not found at {dev_server_path}")

    # Start dev_server subprocess
    env = os.environ.copy()
    env["LOCAL_MODE"] = "true"
    env["ENVIRONMENT"] = "development"

    process = subprocess.Popen(
        [sys.executable, str(dev_server_path)],
        cwd=str(repo_root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    # Wait for dev_server to start (max 30s)
    print("[STARTUP] Waiting for dev_server to start...", flush=True)
    start_time = time.time()
    while time.time() - start_time < 30:
        if is_port_open(3001):
            print("[STARTUP] [OK] Dev server started successfully on localhost:3001", flush=True)
            return process
        time.sleep(0.5)

    print("[STARTUP] [FAIL] Dev server failed to start within 30s", flush=True)
    process.terminate()
    stdout, stderr = process.communicate(timeout=5)
    print(f"[STARTUP] stdout:\n{stdout}")
    print(f"[STARTUP] stderr:\n{stderr}")
    raise RuntimeError("Dev server startup timeout")


def start_dashboard(watch_interval: int | None = None) -> int:
    """Start dashboard (blocks until user exits)."""
    print("[STARTUP] [OK] All prerequisites met. Starting dashboard...", flush=True)
    print("[STARTUP] Press Ctrl+C to stop both dashboard and dev_server", flush=True)
    print()

    repo_root = Path(__file__).parent
    os.chdir(repo_root)

    # Ensure dashboard gets LOCAL_MODE env var
    env = os.environ.copy()
    env["LOCAL_MODE"] = "true"
    env["ENVIRONMENT"] = "development"

    dashboard_args = [sys.executable, "-m", "dashboard", "--local"]

    if watch_interval:
        dashboard_args.extend(["-w", str(watch_interval)])

    # Run dashboard in foreground (blocks until user exits)
    try:
        return subprocess.call(dashboard_args, env=env)
    except KeyboardInterrupt:
        return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Start dashboard with automatic dev_server management",
        epilog="Example: python start_dashboard_dev.py -w 30",
    )
    parser.add_argument(
        "-w",
        "--watch",
        type=int,
        dest="watch_interval",
        help="Enable watch mode with auto-refresh interval (seconds, 10-600)",
        metavar="SECONDS",
    )

    args = parser.parse_args()

    # Validate watch interval if provided
    if args.watch_interval:
        if not (10 <= args.watch_interval <= 600):
            print(f"Error: Watch interval must be 10-600 seconds (got {args.watch_interval})", file=sys.stderr)
            return 1

    try:
        # Load fresh data first (non-critical, continues even if loaders fail)
        run_morning_loaders()

        # Start dev_server (if needed)
        dev_server_process = start_dev_server()

        # Start dashboard (blocks until user exits)
        dashboard_exit_code = start_dashboard(args.watch_interval)

        # Clean up dev_server when dashboard exits
        if dev_server_process:
            print("\n[STARTUP] Shutting down dev_server...", flush=True)
            dev_server_process.terminate()
            try:
                dev_server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                dev_server_process.kill()

        return dashboard_exit_code

    except KeyboardInterrupt:
        print("\n[STARTUP] Interrupted by user", flush=True)
        return 1
    except Exception as e:
        print(f"\n[STARTUP] Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
