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
    # Check both IPv4 and IPv6 localhost addresses to support systems with IPv6-first networking
    localhost_addrs = [("127.0.0.1", socket.AF_INET), ("::1", socket.AF_INET6)]

    for host, family in localhost_addrs:
        try:
            sock = socket.socket(family, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                logger.debug(f"[PORT_CHECK] Port {port} is open on {host}")
                return True
        except Exception as e:
            logger.debug(
                f"[PORT_CHECK] Port check on {host}:{port}: {type(e).__name__}: {e}"
            )
            continue

    return False


def cleanup_orphaned_dev_servers() -> None:
    """Kill any stuck/orphaned dev_server processes to prevent port conflicts."""
    try:
        if sys.platform == "win32":
            # Windows: find PID holding port 3001 and kill it
            # Use netstat to find what PID has port 3001 open
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in result.stdout.split("\n"):
                if "3001" in line and "LISTENING" in line:
                    # Line format: "TCP    127.0.0.1:3001         0.0.0.0:0              LISTENING       12345"
                    parts = line.split()
                    if len(parts) >= 5:
                        try:
                            pid = int(parts[-1])
                            logger.info(f"[STARTUP] Found process {pid} holding port 3001, killing it...")
                            subprocess.run(
                                ["taskkill", "/PID", str(pid), "/F"],
                                capture_output=True,
                                timeout=5,
                            )
                        except (ValueError, subprocess.TimeoutExpired):
                            pass
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
    """Check if key metrics tables are stale (>12 hours old).

    Uses created_at to reflect batch load time (like monitor_data_staleness.py does).
    Changed from 24h to 12h to ensure quality_metrics/value_metrics/growth_metrics are
    refreshed at least twice daily for Phase 7 signal generation. Phase 7 needs fresh
    fundamentals data to properly score signals used in Phase 8 entry execution.
    Session Current: 24h threshold caused Phase 7 lock contention when metrics pipeline
    didn't run, blocking signal quality score computation (root cause: Session 430 issue).

    Returns: (is_stale: bool, reason: str)
    - True if growth_metrics or quality_metrics batches are >12h old (created_at)
    - False if fresh or no data to check
    """
    try:
        from datetime import datetime, timedelta, timezone

        from utils.db import DatabaseContext

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

                staleness_threshold = now - timedelta(hours=12)

                if latest_growth < staleness_threshold or latest_quality < staleness_threshold:
                    hours_old = min(
                        (now - latest_growth).total_seconds() / 3600,
                        (now - latest_quality).total_seconds() / 3600
                    )
                    return True, f"growth_metrics/quality_metrics batches {hours_old:.1f}h stale (>12h)"
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
        print(f"[STARTUP] [ERROR] Loader scheduler not found at {scheduler_path}", flush=True)
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


def check_if_run_already_complete(run_type: str) -> bool:
    """Check if a run (morning/metrics/signals) already completed successfully today.

    Returns True if run already completed, False if it needs to run or check failed.
    """
    try:
        from datetime import date
        from utils.db import DatabaseContext

        today = date.today()
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT run_id, overall_status, started_at
                FROM orchestrator_execution_log
                WHERE run_date = %s AND run_id ILIKE %s AND overall_status = 'success'
                ORDER BY started_at DESC LIMIT 1
                """,
                (today, f"LOCAL-{run_type.upper()}-%"),
            )
            row = cur.fetchone()
            return row is not None
    except Exception as e:
        print(f"[STARTUP] [WARN] Could not check if {run_type} already ran: {e}", flush=True)
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

    # Step 1: Check if morning pipeline already ran today - skip if it did
    if check_if_run_already_complete("morning"):
        print("[STARTUP] Step 1/3: Morning pipeline (prices, technicals, market status)...", flush=True)
        print("[STARTUP] [OK] Morning pipeline already ran today - skipping", flush=True)
        morning_ok = True
    else:
        # Step 1: Run morning pipeline (prices, technicals)
        # 7 loaders (incl. rate-limited SEC/FINRA/Playwright fetches) over the full symbol
        # universe (5459 active symbols as of the stock_symbols NYSE-listing fix) routinely
        # exceed 10 minutes - a too-short timeout here silently truncates the pipeline
        # mid-loader every run, which is why price_daily/technical_data_daily kept going
        # stale even when this startup script ran. 1800s matches the metrics pipeline budget.
        print("[STARTUP] Step 1/3: Morning pipeline (prices, technicals, market status)...", flush=True)
        morning_ok = run_loader_pipeline("morning", timeout=1800)

    if not morning_ok:
        # FAIL-FAST: Morning pipeline must succeed - it loads prices and technicals
        # required for all 9 orchestrator phases. Proceeding with stale data violates
        # fail-fast principle and risks trading on stale market data.
        msg = "[STARTUP] CRITICAL: Morning pipeline failed. Dashboard cannot start with stale price/technical data. Fix data loaders and retry."
        print(msg, flush=True)
        raise RuntimeError(msg)

    # Step 2: Check if the slow fundamentals pipeline is needed (metrics table staleness)
    # Don't use stock_scores completeness as gate - that gate was too aggressive and caused
    # metrics tables to become stale even when scores were complete. Instead, check if the
    # actual metrics tables (growth_metrics, quality_metrics) are stale (>12h old).
    is_stale, staleness_reason = check_metrics_tables_staleness()
    print(f"[STARTUP] Metrics table staleness check: {staleness_reason}", flush=True)

    if is_stale:
        print("[STARTUP] Step 2/3: Metrics pipeline (SEC fundamentals: financials, 13F, insider, value/quality/growth)...", flush=True)
        print("[STARTUP]          (This may take 10-20 minutes on first run)", flush=True)
        metrics_ok = run_loader_pipeline("metrics", timeout=1800)  # 30 min for metrics

        if not metrics_ok:
            # NON-CRITICAL: Metrics pipeline failure means fundamentals data remains stale.
            # This is not ideal for signal quality, but the dashboard can still function with
            # yesterday's fundamental data while trading on today's prices. Signals will still
            # generate and trade (based on price action) - they just won't have today's earnings
            # or 13F updates. Continue startup to avoid blocking the entire platform.
            print("[STARTUP] [WARN] Metrics pipeline failed - fundamentals data remains stale, but dashboard can still function", flush=True)
            print("[STARTUP] [WARN] If signal quality degrades, re-run orchestrator or restart dashboard after metrics pipeline succeeds", flush=True)
    else:
        print(f"[STARTUP] Metrics tables are fresh - skipping metrics pipeline ({staleness_reason})", flush=True)

    # Step 3: Check if signals pipeline already ran today - skip if it did
    # Signals pipeline is price-driven, so it should run whenever prices update (always on
    # dashboard startup to ensure signals reflect today's prices). However, if it already ran
    # earlier today, skip the re-run to avoid unnecessary load.
    if check_if_run_already_complete("signals"):
        print("[STARTUP] Step 3/3: Signals pipeline (closing prices, stock scores, buy/sell signals, risk metrics)...", flush=True)
        print("[STARTUP] [OK] Signals pipeline already ran today - skipping", flush=True)
        signals_ok = True
    else:
        print("[STARTUP] Step 3/3: Signals pipeline (closing prices, stock scores, buy/sell signals, risk metrics)...", flush=True)
        signals_ok = run_loader_pipeline("signals", timeout=1800)

    if signals_ok:
        completeness = check_stock_scores_completeness()
        print(f"[STARTUP] [OK] Stock scores recomputed: {completeness:.1f}%", flush=True)
    else:
        # FAIL-FAST: Signal generation failure means buy/sell signals cannot be generated.
        # Dashboard would show no signals - no point in running without the core signal data.
        msg = "[STARTUP] CRITICAL: Signals pipeline failed. Buy/sell signals, stock scores, and risk metrics cannot be computed. Dashboard cannot start without signals data."
        print(msg, flush=True)
        raise RuntimeError(msg)

    print("[STARTUP] [OK] Data refresh complete", flush=True)
    print("[STARTUP] ============================================================", flush=True)
    return True


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


def start_react_dev_server() -> subprocess.Popen | None:
    """Start React dev server (Vite) for web UI on port 5173+."""
    try:
        react_dir = Path(__file__).parent / "webapp" / "frontend"
        if not react_dir.exists():
            logger.warning(f"[REACT] React directory not found: {react_dir}")
            return None

        logger.info("[REACT] Starting React dev server (Vite)...")
        logger.info(f"[REACT] Working directory: {react_dir}")

        # Start React dev server with npm run dev
        # Vite will automatically find an available port (5173, 5174, 5175, etc.)
        process = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=str(react_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        # Wait for React dev server to be ready
        logger.info("[REACT] Waiting for React dev server to be ready (max 30s)...")
        max_wait = 30
        start_time = time.time()
        react_port = None

        # Read output to find the port
        import threading

        def read_output():
            nonlocal react_port
            if process.stdout:
                for line in process.stdout:
                    print(f"[REACT] {line.rstrip()}")
                    if "Local:" in line and "http://localhost:" in line:
                        try:
                            port_str = line.split("localhost:")[1].split("/")[0]
                            react_port = int(port_str)
                        except (ValueError, IndexError):
                            pass

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()

        # Wait for port to be detected or timeout
        while react_port is None and (time.time() - start_time) < max_wait:
            time.sleep(1)

        if react_port:
            logger.info(f"[REACT] Dev server ready on http://localhost:{react_port}")
        else:
            logger.warning("[REACT] Could not detect port, checking if process is running...")
            if process.poll() is not None:
                stderr = process.stderr.read() if process.stderr else "unknown error"
                logger.error(f"[REACT] Process exited: {stderr}")
                return None

        logger.info("[REACT] React web UI is available")
        return process

    except FileNotFoundError:
        logger.error("[REACT] npm not found. Install Node.js to use React dev server.")
        return None
    except Exception as e:
        logger.error(f"[REACT] Failed to start React dev server: {e}")
        return None


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
        # Runs on all platforms (including Windows) - loaders are verified working end-to-end
        run_complete_loader_pipeline()

        # Start dev_server (if needed)
        dev_server_process = start_dev_server()

        # Start React dev server for web UI
        react_process = start_react_dev_server()

        # Start dashboard (blocks until user exits)
        dashboard_exit_code = start_dashboard(args.watch_interval)

        # Clean up processes when dashboard exits
        if react_process:
            print("\n[STARTUP] Shutting down React dev server...", flush=True)
            react_process.terminate()
            try:
                react_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                react_process.kill()

        if dev_server_process:
            print("\n[STARTUP] Shutting down API dev_server...", flush=True)
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
