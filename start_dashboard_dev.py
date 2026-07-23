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
import logging
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

# Configure logging early so all messages are captured
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Load .env.local credentials BEFORE any imports
from utils.dotenv_loader import load_env_local

load_env_local()

# Load Alpaca credentials from database (persistent storage, not files)
try:
    project_root = Path(__file__).parent
    sys.path.insert(0, str(project_root))
    from scripts.load_credentials import ensure_credentials_loaded
    ensure_credentials_loaded()
except Exception as e:
    # Log but don't crash - credentials might come from environment
    logger.warning(f"[CREDS] Could not load credentials from database: {e}")
    logger.warning("[CREDS] Continuing - credentials may be in environment variables or .env.local")


def is_port_open(port: int, timeout: float = 1.0) -> bool:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex(("127.0.0.1", port))
        sock.close()
        return result == 0
    except Exception as e:
        logger.warning(
            f"[PORT_CHECK] Port check failed for 127.0.0.1:{port}: "
            f"{type(e).__name__}: {e}. Assuming port is unavailable."
        )
        return False


def cleanup_orphaned_dev_servers() -> None:
    """Kill any stuck/orphaned dev_server processes to prevent port conflicts."""
    try:
        if sys.platform == "win32":
            # Windows: use taskkill to kill only dev_server processes
            subprocess.run(
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
        time.sleep(1)
    except subprocess.TimeoutExpired as e:
        logger.warning(
            f"[STARTUP] Dev server cleanup timed out: {type(e).__name__}: {e}. "
            "Port may still be in use by orphaned process."
        )
    except Exception as e:
        logger.warning(
            f"[STARTUP] Dev server cleanup failed: {type(e).__name__}: {e}. "
            "Proceeding despite cleanup failure - port may conflict if orphaned process still running."
        )


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


def check_metrics_tables_staleness() -> tuple[bool, str]:
    """Check if key metrics tables are stale (>24 hours old).

    Uses created_at to reflect batch load time (like monitor_data_staleness.py does).

    Returns: (is_stale: bool, reason: str)
    - True if growth_metrics or quality_metrics batches are >24h old (created_at)
    - False if fresh or no data to check
    """
    try:
        from utils.db import DatabaseContext
        from datetime import datetime, timedelta, timezone

        with DatabaseContext("read") as cur:
            # Check growth_metrics and quality_metrics batch staleness (created_at = batch load time)
            cur.execute("""
                SELECT
                    COALESCE(MAX(created_at), NOW() - INTERVAL '48 hours') as latest_growth,
                    (SELECT COALESCE(MAX(created_at), NOW() - INTERVAL '48 hours')
                     FROM quality_metrics) as latest_quality
                FROM growth_metrics
            """)
            row = cur.fetchone()
            if row:
                now = datetime.now(timezone.utc)
                latest_growth = row[0] if isinstance(row[0], datetime) else now
                latest_quality = row[1] if isinstance(row[1], datetime) else now

                # Ensure tz-aware comparison
                if latest_growth.tzinfo is None:
                    latest_growth = latest_growth.replace(tzinfo=timezone.utc)
                if latest_quality.tzinfo is None:
                    latest_quality = latest_quality.replace(tzinfo=timezone.utc)

                staleness_threshold = now - timedelta(hours=24)

                if latest_growth < staleness_threshold or latest_quality < staleness_threshold:
                    hours_old = min(
                        (now - latest_growth).total_seconds() / 3600,
                        (now - latest_quality).total_seconds() / 3600
                    )
                    return True, f"growth_metrics/quality_metrics batches {hours_old:.1f}h stale (>24h)"
                else:
                    hours_old = min(
                        (now - latest_growth).total_seconds() / 3600,
                        (now - latest_quality).total_seconds() / 3600
                    )
                    return False, f"metrics batches fresh ({hours_old:.1f}h old)"

            return False, "no metrics data found"
    except Exception as e:
        print(f"[STARTUP] [WARN] Could not check metrics staleness: {e}", flush=True)
        return False, f"staleness check failed: {e}"


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
    """Run COMPLETE loader pipeline: morning + (conditional) metrics + signals.

    Ensures dashboard has fresh data for all 9 orchestrator phases:
    1. Morning pipeline: prices, technicals, market status
    2. Metrics pipeline: slow SEC/EDGAR fundamentals (financial statements, 13F, insider,
       positioning, quality/growth/value) - skipped once stock_scores completeness is high,
       since fundamentals rarely change day to day and re-fetching from SEC/EDGAR takes
       10-20 minutes.
    3. Signals pipeline: re-fetches closing prices/technicals, then recomputes stock_scores/
       buy_sell_daily/signal_quality_scores/risk_metrics/algo_metrics/sector_industry. ALWAYS
       runs, regardless of the metrics completeness gate above - these are price-driven (not
       fundamentals-driven) and are what the dashboard's trading signals actually display.
       Bug fixed 2026-07-21: these 6 loaders used to live inside "metrics" and were silently
       skipped by the completeness gate on every run after the first (fundamentals completeness
       stays >=75% indefinitely once first achieved), so the dashboard kept refreshing prices/
       technicals every launch while buy/sell signals silently froze at whatever day "metrics"
       last actually ran - no warning shown anywhere.

    Returns True if successful, False if loaders failed/timed out.
    Non-critical: dashboard will still start even if loaders fail, just with stale data.
    """
    print("[STARTUP] ============================================================", flush=True)
    print("[STARTUP] REFRESHING DATA: Running complete loader pipeline", flush=True)
    print("[STARTUP] ============================================================", flush=True)

    # Step 1: Run morning pipeline (prices, technicals)
    # 7 loaders (incl. rate-limited SEC/FINRA/Playwright fetches) over the full symbol
    # universe (5459 active symbols as of the stock_symbols NYSE-listing fix) routinely
    # exceed 10 minutes - a too-short timeout here silently truncates the pipeline
    # mid-loader every run, which is why price_daily/technical_data_daily kept going
    # stale even when this startup script ran. 1800s matches the metrics pipeline budget.
    print("[STARTUP] Step 1/3: Morning pipeline (prices, technicals, market status)...", flush=True)
    morning_ok = run_loader_pipeline("morning", timeout=1800)

    if not morning_ok:
        print("[STARTUP] [WARN] Morning pipeline failed - proceeding with stale data", flush=True)

    # Step 2: Check if the slow fundamentals pipeline is needed (metrics table staleness)
    # Don't use stock_scores completeness as gate - that gate was too aggressive and caused
    # metrics tables to become stale even when scores were complete. Instead, check if the
    # actual metrics tables (growth_metrics, quality_metrics) are stale (>24h old).
    is_stale, staleness_reason = check_metrics_tables_staleness()
    print(f"[STARTUP] Metrics table staleness check: {staleness_reason}", flush=True)

    if is_stale:
        print("[STARTUP] Step 2/3: Metrics pipeline (SEC fundamentals: financials, 13F, insider, value/quality/growth)...", flush=True)
        print("[STARTUP]          (This may take 10-20 minutes on first run)", flush=True)
        metrics_ok = run_loader_pipeline("metrics", timeout=1800)  # 30 min for metrics

        if not metrics_ok:
            print("[STARTUP] [WARN] Metrics pipeline failed - fundamentals may be stale", flush=True)
    else:
        print(f"[STARTUP] Metrics tables are fresh - skipping metrics pipeline ({staleness_reason})", flush=True)

    # Step 3: ALWAYS re-fetch closing prices/technicals and regenerate scores/signals from them.
    # Must run every launch so the dashboard's buy/sell signals reflect today's prices, not
    # whatever day metrics last ran. Includes a price/technical re-fetch (like "morning"), so
    # uses the same 1800s budget rather than the shorter timeout the DB-only steps alone would need.
    print("[STARTUP] Step 3/3: Signals pipeline (closing prices, stock scores, buy/sell signals, risk metrics)...", flush=True)
    signals_ok = run_loader_pipeline("signals", timeout=1800)

    if signals_ok:
        completeness = check_stock_scores_completeness()
        print(f"[STARTUP] [OK] Stock scores recomputed: {completeness:.1f}%", flush=True)
    else:
        print("[STARTUP] [WARN] Signals pipeline failed - Phase 7 signal generation will be limited", flush=True)

    print("[STARTUP] [OK] Data refresh complete", flush=True)
    print("[STARTUP] ============================================================", flush=True)
    return morning_ok and signals_ok


def start_dev_server() -> subprocess.Popen:
    """Start dev_server in background and wait for it to be ready."""
    print("[STARTUP] Checking if dev_server (localhost:3001) is already running...", flush=True)

    # Check if already running
    if is_port_open(3001):
        from utils.dev_server_state import is_running_server_stale

        repo_root = Path(__file__).parent
        if is_running_server_stale(repo_root):
            print(
                "[STARTUP] [WARN] Dev server is running but its code is stale (source files "
                "changed since it started - dev_server.py never hot-reloads). Restarting to "
                "pick up the latest code...",
                flush=True,
            )
        else:
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
