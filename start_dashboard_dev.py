#!/usr/bin/env python3
"""Unified dashboard startup script for local development.

Automatically runs COMPLETE loader pipeline before starting dashboard:
1. Morning pipeline: prices, technicals, market status (5-10 min)
2. Metrics pipeline: financial data, quality/growth/value scores (5-10 min, only if needed)
3. Dev server: API backend
4. Dashboard: Web UI

This ensures dashboard has fresh data across all 9 orchestrator phases.

Usage:
    python start_dashboard_dev.py              # Start with auto-refresh disabled
    python start_dashboard_dev.py -w 30        # Start with auto-refresh every 30s
    python start_dashboard_dev.py --help       # Show all options

First run may take 10-20 minutes as metrics pipeline refreshes financial data.
Subsequent runs faster if stock_scores already complete.
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


def check_stock_scores_completeness() -> float:
    """Check what percentage of stocks have complete composite_score.

    Returns percentage (0-100) of stocks with scores.
    """
    try:
        from utils.db import DatabaseContext

        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE composite_score IS NOT NULL) as scored
                FROM stock_scores
            """)
            row = cur.fetchone()
            if row and row[0] > 0:
                return (row[1] / row[0]) * 100
            return 0
    except Exception as e:
        print(f"[STARTUP] [WARN] Could not check stock_scores completeness: {e}", flush=True)
        return 0


def run_loader_pipeline(pipeline_name: str, timeout: int = 3600) -> bool:
    """Run a loader pipeline using local_loader_scheduler.

    Args:
        pipeline_name: 'morning' or 'metrics'
        timeout: Maximum seconds to wait (default 1 hour)

    Returns: True if successful, False if failed/timed out
    """
    repo_root = Path(__file__).parent
    scheduler_path = repo_root / "scripts" / "local_loader_scheduler.py"

    if not scheduler_path.exists():
        print(f"[STARTUP] [WARN] Loader scheduler not found at {scheduler_path}", flush=True)
        return False

    print(f"[STARTUP] Running {pipeline_name} loader pipeline (timeout: {timeout}s)...", flush=True)

    try:
        env = os.environ.copy()
        env["LOCAL_MODE"] = "1"
        result = subprocess.run(
            [sys.executable, str(scheduler_path), "--now", pipeline_name],
            cwd=str(repo_root),
            env=env,
            timeout=timeout,
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            print(f"[STARTUP] [OK] {pipeline_name} pipeline completed successfully", flush=True)
            return True
        else:
            print(f"[STARTUP] [WARN] {pipeline_name} pipeline failed (exit code {result.returncode})", flush=True)
            if result.stderr:
                print(f"[STARTUP] stderr: {result.stderr[:200]}", flush=True)
            return False
    except subprocess.TimeoutExpired:
        print(f"[STARTUP] [WARN] {pipeline_name} pipeline timed out after {timeout}s", flush=True)
        return False
    except Exception as e:
        print(f"[STARTUP] [WARN] {pipeline_name} pipeline error: {e}", flush=True)
        return False


def run_complete_loader_pipeline() -> bool:
    """Run COMPLETE loader pipeline: morning + metrics.

    Ensures dashboard has fresh data for all 9 orchestrator phases:
    1. Morning pipeline: prices, technicals, market status
    2. Metrics pipeline: financial statements, quality/growth/value scores

    Returns True if successful, False if loaders failed/timed out.
    Non-critical: dashboard will still start even if loaders fail, just with stale data.
    """
    print("[STARTUP] ============================================================", flush=True)
    print("[STARTUP] REFRESHING DATA: Running complete loader pipeline", flush=True)
    print("[STARTUP] ============================================================", flush=True)

    # Step 1: Run morning pipeline (prices, technicals)
    print("[STARTUP] Step 1/2: Morning pipeline (prices, technicals, market status)...", flush=True)
    morning_ok = run_loader_pipeline("morning", timeout=600)

    if not morning_ok:
        print("[STARTUP] [WARN] Morning pipeline failed - proceeding with stale data", flush=True)

    # Step 2: Check if metrics pipeline needed (stock_scores completeness)
    completeness = check_stock_scores_completeness()
    print(f"[STARTUP] Stock scores completeness: {completeness:.1f}%", flush=True)

    if completeness < 75:
        print("[STARTUP] Step 2/2: Metrics pipeline (financial data, quality/growth/value scores)...", flush=True)
        print("[STARTUP]          (This may take 5-10 minutes on first run)", flush=True)
        metrics_ok = run_loader_pipeline("metrics", timeout=1800)  # 30 min for metrics

        if metrics_ok:
            completeness = check_stock_scores_completeness()
            print(f"[STARTUP] [OK] Stock scores updated: {completeness:.1f}%", flush=True)
        else:
            print("[STARTUP] [WARN] Metrics pipeline failed - Phase 7 signal generation will be limited", flush=True)
    else:
        print("[STARTUP] Stock scores already complete - skipping metrics pipeline", flush=True)

    print("[STARTUP] [OK] Data refresh complete", flush=True)
    print("[STARTUP] ============================================================", flush=True)
    return morning_ok


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
    env["ALPACA_PAPER_TRADING"] = "true"  # CRITICAL: Ensure paper trading mode for local dev

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
        # Runs complete pipeline: morning (prices/technicals) + metrics (financial/scores)
        run_complete_loader_pipeline()

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
