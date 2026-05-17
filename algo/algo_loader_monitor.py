#!/usr/bin/env python3

"""
Loader Failure Monitor — Detects when data loaders fail silently

Watches for missing data by checking:
1. Per-symbol freshness (alerts if critical symbols have no data)
2. Daily data count (alerts if load volume drops)
3. Loader success/failure patterns
4. ECS task execution status (for cloud deployments)

Integrates with Phase 1 of the orchestrator to fail-closed on stale data.

USAGE:
  python3 algo_loader_monitor.py --check-symbols BRK.B,LEN.B,WSO.B
  python3 algo_loader_monitor.py --check-freshness
"""

from config.credential_helper import get_db_config
from config.env_loader import load_env
from config.credential_helper import get_db_password, get_db_config

try:
    from config.credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

import os
from utils.db_connection import get_db_connection
import argparse
from pathlib import Path
from datetime import date as _date, datetime, timedelta
from algo.algo_sql_safety import assert_safe_table, assert_safe_column
from utils.structured_logger import get_logger

logger = get_logger(__name__)

def main():
    parser = argparse.ArgumentParser(description="Monitor data loader health")
    parser.add_argument(
        "--check-symbols",
        help="Comma-separated symbols to check (e.g., BRK.B,LEN.B,WSO.B)",
    )
    parser.add_argument(
        "--check-freshness",
        action="store_true",
        help="Run all freshness checks",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    args = parser.parse_args()

    monitor = LoaderMonitor()
    monitor.connect()

    try:
        symbols = []
        if args.check_symbols:
            symbols = [s.strip().upper() for s in args.check_symbols.split(",")]
        elif args.check_freshness:
            symbols = None
        else:
            symbols = ["AAPL", "MSFT", "NVDA", "TSLA"]  # Default critical symbols

        monitor.audit_all(critical_symbols=symbols)
        monitor.report(json_format=args.json)

        # Exit with error code if critical findings
        has_critical = any(f[0] == "CRITICAL" for f in monitor.findings)
        return 1 if has_critical else 0

    finally:
        monitor.disconnect()

if __name__ == "__main__":
    exit(main())

