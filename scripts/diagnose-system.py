#!/usr/bin/env python3
"""Comprehensive system diagnostic to identify what's broken."""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.db.context import DatabaseContext
from utils.db.sql_safety import assert_safe_table
from utils.infrastructure.timezone import EASTERN_TZ

def check_database_connection():
    """Test database connectivity."""
    try:
        with DatabaseContext('read') as cur:
            cur.execute("SELECT now() AT TIME ZONE 'UTC'")
            result = cur.fetchone()
            print("[OK] Database connected")
            return True
    except Exception as e:
        print(f"[FAIL] Database connection: {e}")
        return False

def check_loader_status():
    """Check status of critical loaders."""
    print("\n=== LOADER STATUS ===")
    try:
        with DatabaseContext('read') as cur:
            cur.execute("""
                SELECT table_name, status, last_updated, row_count
                FROM data_loader_status
                ORDER BY last_updated DESC
            """)
            rows = cur.fetchall()

            failed = []
            passed = []
            for row in rows:
                name, status, updated, count = row[0], row[1], row[2], row[3]
                if status == 'FAILED':
                    failed.append(name)
                    print(f"[FAIL] {name:<30} FAILED - last updated: {updated}")
                elif status == 'COMPLETED':
                    passed.append(name)

            print(f"\nPassed: {len(passed)} loaders")
            print(f"Failed: {len(failed)} loaders")
            if failed:
                print(f"Failed loaders: {', '.join(failed)}")
            return len(failed) == 0

    except Exception as e:
        print(f"[ERROR] Could not check loader status: {e}")
        return False

def check_critical_tables():
    """Check if critical tables have recent data."""
    print("\n=== CRITICAL TABLES ===")
    critical_tables = [
        'stock_symbols',
        'technical_data_daily',
        'market_health_daily',
        'buy_sell_daily',
        'signal_quality_scores',
        'swing_trader_scores',
        'market_exposure_daily',
        'algo_positions',
        'circuit_breaker_metrics',
        'algo_performance_metrics',
    ]

    try:
        with DatabaseContext('read') as cur:
            healthy = []
            for table in critical_tables:
                try:
                    table_safe = assert_safe_table(table)
                    cur.execute(f"SELECT COUNT(*) FROM {table_safe}")
                    count = cur.fetchone()[0]
                    print(f"[OK] {table:<30} {count:>10,} rows")
                    if count > 0:
                        healthy.append(table)
                except Exception as e:
                    print(f"[WARN] {table:<30} - {str(e)[:50]}")

            return len(healthy) >= 8

    except Exception as e:
        print(f"[ERROR] Could not check tables: {e}")
        return False

def check_data_freshness():
    """Check if data is current (updated today)."""
    print("\n=== DATA FRESHNESS ===")
    try:
        today_et = datetime.now(EASTERN_TZ).date()

        with DatabaseContext('read') as cur:
            # Check technical_data_daily
            cur.execute("""
                SELECT MAX(date) FROM technical_data_daily
            """)
            max_date = cur.fetchone()[0]

            if max_date:
                days_old = (today_et - max_date).days
                status = "[OK]" if days_old <= 1 else "[WARN]"
                print(f"{status} technical_data_daily: {max_date} ({days_old} days old)")
            else:
                print("[FAIL] technical_data_daily: No data")

            # Check market_health_daily
            cur.execute("""
                SELECT MAX(date) FROM market_health_daily
            """)
            max_date = cur.fetchone()[0]

            if max_date:
                days_old = (today_et - max_date).days
                status = "[OK]" if days_old <= 1 else "[WARN]"
                print(f"{status} market_health_daily: {max_date} ({days_old} days old)")
            else:
                print("[FAIL] market_health_daily: No data")

            # Check algorithm positions
            cur.execute("""
                SELECT COUNT(*) FROM algo_positions WHERE status = 'OPEN'
            """)
            open_positions = cur.fetchone()[0]
            print(f"[OK] algo_positions: {open_positions} open positions")

            return True

    except Exception as e:
        print(f"[ERROR] Could not check freshness: {e}")
        return False

def check_orchestrator_status():
    """Check if orchestrator ran recently."""
    print("\n=== ORCHESTRATOR ===")
    try:
        with DatabaseContext('read') as cur:
            cur.execute("""
                SELECT run_date, overall_status FROM algo_orchestrator_runs
                ORDER BY run_date DESC LIMIT 1
            """)
            row = cur.fetchone()
            if row:
                run_date, status = row[0], row[1]
                hours_ago = (datetime.now(timezone.utc) - run_date).total_seconds() / 3600
                print(f"[OK] Last orchestrator run: {run_date} ({hours_ago:.1f} hours ago)")
                print(f"     Status: {status}")
            else:
                print("[WARN] No orchestrator runs found")
            return True
    except Exception as e:
        print(f"[ERROR] Could not check orchestrator: {e}")
        return False

def main():
    print("=" * 70)
    print("SYSTEM DIAGNOSTIC REPORT")
    print("=" * 70)

    checks = [
        ("Database Connection", check_database_connection()),
        ("Loader Status", check_loader_status()),
        ("Critical Tables", check_critical_tables()),
        ("Data Freshness", check_data_freshness()),
        ("Orchestrator", check_orchestrator_status()),
    ]

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    for name, passed in checks:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {name}")

    all_passed = all(passed for _, passed in checks)

    if all_passed:
        print("\n[OK] System is healthy")
        return 0
    else:
        print("\n[FAIL] System has issues - see above for details")
        return 1

if __name__ == '__main__':
    sys.exit(main())
