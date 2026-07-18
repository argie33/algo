#!/usr/bin/env python3
"""Start complete local development environment.

Launches all services needed for local development:
1. PostgreSQL check
2. Dev server (lambda API on localhost:3001)
3. Initial data load (if needed)
4. Dashboard
5. Background orchestrator/loader monitor

Usage:
  python start_dev.py                    # Start everything, monitor with dashboard
  python start_dev.py --check-only       # Check status without starting services
  python start_dev.py --no-dashboard     # Start services but don't open dashboard
  python start_dev.py --refresh-data     # Run loaders first, then start services
"""

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

# Set development mode
os.environ["LOCAL_MODE"] = "true"
os.environ["ENVIRONMENT"] = "development"
os.environ["SKIP_ORCHESTRATOR_LOCK"] = "true"


def check_postgres() -> bool:
    """Check if PostgreSQL is running."""
    try:
        result = subprocess.run(
            ["python", "-c",
             "import psycopg2; c = psycopg2.connect('dbname=stocks user=stocks host=localhost'); c.close()"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


def check_dev_server() -> bool:
    """Check if dev server is running."""
    try:
        result = subprocess.run(
            ["curl", "-s", "http://localhost:3001/api/health"],
            capture_output=True,
            timeout=3
        )
        return result.returncode == 0
    except Exception:
        return False


def start_service(cmd: list[str], name: str, wait_for_ready: bool = False) -> subprocess.Popen | None:
    """Start a background service."""
    print(f"  Starting {name}...", end=" ", flush=True)
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        if wait_for_ready:
            # Wait for service to be ready
            max_retries = 10
            for attempt in range(max_retries):
                time.sleep(1)
                if name == "Dev Server" and check_dev_server():
                    print("[OK]")
                    return process
                elif name != "Dev Server":
                    print("[OK]")
                    return process

            print("[TIMEOUT]")
            return process
        else:
            print("[OK]")
            return process
    except Exception as e:
        print(f"[ERROR] {e}")
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Start local development environment")
    parser.add_argument("--check-only", action="store_true", help="Check status without starting")
    parser.add_argument("--no-dashboard", action="store_true", help="Don't open dashboard")
    parser.add_argument("--refresh-data", action="store_true", help="Refresh data before starting")
    args = parser.parse_args()

    et = ZoneInfo("America/New_York")
    now = datetime.now(et)

    print("\n" + "="*70)
    print("LOCAL DEVELOPMENT ENVIRONMENT")
    print("="*70)
    print(f"Time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print("Mode: LOCAL_MODE=true")
    print()

    # Check prerequisites
    print("Prerequisites:")
    print("  PostgreSQL...", end=" ", flush=True)
    pg_ok = check_postgres()
    print("[OK]" if pg_ok else "[FAIL]")

    if not pg_ok:
        print("\n❌ PostgreSQL not running!")
        print("   Start PostgreSQL and try again:")
        print("   • Windows: psql -U stocks -d stocks")
        print("   • macOS/Linux: psql -U stocks -d stocks")
        sys.exit(1)

    # Check dev server
    dev_ok = check_dev_server()
    print("  Dev Server...", end=" ", flush=True)
    print("[RUNNING]" if dev_ok else "[NOT RUNNING]")

    if args.check_only:
        print("\n✅ Ready to start!")
        sys.exit(0)

    print()

    # Refresh data if requested
    if args.refresh_data:
        print("Refreshing data (this may take 10-20 minutes)...")
        result = subprocess.run(
            ["python", "run_dev_pipeline.py", "--fast"],
            capture_output=False
        )
        if result.returncode != 0:
            print("\n⚠️ Data refresh encountered issues (proceeding anyway)")

    # Start services
    print("\nStarting services:")
    services = []

    # Start dev server if not running
    if not dev_ok:
        process = start_service(
            ["python", "lambda/api/dev_server.py"],
            "Dev Server",
            wait_for_ready=True
        )
        if process:
            services.append(process)
    else:
        print("  Dev Server... [ALREADY RUNNING]")

    # Start background orchestrator monitor
    # (This will run orchestrator on schedule)
    print("  Orchestrator Monitor...", end=" ", flush=True)
    monitor_process = subprocess.Popen(
        ["python", "run_dev_pipeline.py", "--watch", "3600"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print("[OK - runs every 1 hour]")
    services.append(monitor_process)

    print()
    print("="*70)
    print("SERVICES RUNNING")
    print("="*70)
    print("  ✓ PostgreSQL (database)")
    print("  ✓ Dev Server (API on localhost:3001)")
    print("  ✓ Orchestrator Monitor (runs every 1 hour)")
    print()
    print("="*70)
    print("NEXT STEPS")
    print("="*70)

    if not args.no_dashboard:
        print("\nStarting Dashboard...")
        print("  • Dashboard will open automatically on localhost:3000")
        print("  • Exit dashboard with Ctrl+C")
        print("  • Services will keep running")
        print()

        try:
            result = subprocess.run(
                ["python", "dashboard.py", "--local", "-w", "30"],
                text=True
            )
        except KeyboardInterrupt:
            print("\n\nDashboard closed.")

        print("\nServices still running. To stop:")
        print("  • Kill this terminal, or")
        print("  • Services auto-cleanup on exit")
    else:
        print("\nServices running. Dashboard commands:")
        print("  Terminal 1 (dashboard): python dashboard.py --local -w 30")
        print("  Terminal 2 (loader): python run_dev_pipeline.py --morning")
        print("  Check status: python dev_environment_setup.py --check")
        print()
        print("Press Ctrl+C to stop orchestrator monitor...")

        try:
            monitor_process.wait()
        except KeyboardInterrupt:
            print("\n\nStopping services...")
            for process in services:
                process.terminate()
                process.wait(timeout=5)
            print("Done!")


if __name__ == "__main__":
    main()
