#!/usr/bin/env python3
"""Diagnostic script to check pipeline status and identify blocking issues."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from utils.database_context import DatabaseContext
from datetime import datetime, date, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_table_freshness():
    """Check how fresh each critical table is."""
    print("\n" + "="*70)
    print("TABLE FRESHNESS CHECK")
    print("="*70)

    tables_to_check = {
        'price_daily': 'date',
        'market_health_daily': 'date',
        'technical_data_daily': 'date',
        'buy_sell_daily': 'date',
        'signal_quality_scores': 'date',
        'swing_trader_scores': 'date',
        'sector_ranking': 'date',
        'trend_template_data': 'date',
    }

    try:
        with DatabaseContext('read') as cur:
            for table, date_col in tables_to_check.items():
                try:
                    cur.execute(f"""
                        SELECT COUNT(*), MAX({date_col}), MIN({date_col})
                        FROM {table}
                    """)
                    row = cur.fetchone()
                    if row:
                        count, max_date, min_date = row
                        age = (date.today() - max_date).days if max_date else None
                        status = "[OK]" if age and age <= 1 else "[WARN]" if age and age <= 5 else "[FAIL]"
                        print(f"{status} {table:30s} | count={count:7,} | max={max_date} ({age}d old)" +
                              (f" | min={min_date}" if count > 0 else ""))
                    else:
                        print(f"✗ {table:30s} | EMPTY")
                except Exception as e:
                    print(f"✗ {table:30s} | ERROR: {str(e)[:60]}")
    except Exception as e:
        print(f"Connection error: {e}")

def check_schema():
    """Check that critical schemas are correct."""
    print("\n" + "="*70)
    print("SCHEMA VALIDATION")
    print("="*70)

    try:
        with DatabaseContext('read') as cur:
            # Check sector_ranking has 'date' column (not 'date_recorded')
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name='sector_ranking'
            """)
            columns = [row[0] for row in cur.fetchall()]

            if 'date' in columns:
                print("[OK] sector_ranking has 'date' column (migration 015 applied)")
            else:
                print("[FAIL] sector_ranking missing 'date' column (migration 015 NOT applied)")

            if 'date_recorded' in columns:
                print("[WARN] sector_ranking still has 'date_recorded' (should be removed)")

            # Check that we have rank_*_ago columns
            required = ['rank_1w_ago', 'rank_4w_ago', 'rank_12w_ago']
            missing = [c for c in required if c not in columns]
            if missing:
                print(f"[WARN] sector_ranking missing columns: {missing}")
            else:
                print("[OK] sector_ranking has all required rank_*_ago columns")

    except Exception as e:
        print(f"Schema check error: {e}")

def check_migrations():
    """Check which migrations have been applied."""
    print("\n" + "="*70)
    print("MIGRATION STATUS")
    print("="*70)

    try:
        with DatabaseContext('read') as cur:
            cur.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 5")
            rows = cur.fetchall()
            if rows:
                print("Latest 5 applied migrations:")
                for row in rows:
                    version = row[0]
                    print(f"  [OK] {version:40s}")

                # Check specifically for 015
                cur.execute("SELECT 1 FROM schema_version WHERE version = '015_fix_sector_ranking_schema'")
                if cur.fetchone():
                    print("\n[OK] Migration 015 (sector_ranking schema fix) is APPLIED")
                else:
                    print("\n[FAIL] Migration 015 (sector_ranking schema fix) is PENDING")
            else:
                print("No migrations found!")
    except Exception as e:
        print(f"Migration check error: {e}")

def check_loader_status():
    """Check data_loader_status table for hints about what ran last."""
    print("\n" + "="*70)
    print("LOADER STATUS")
    print("="*70)

    try:
        with DatabaseContext('read') as cur:
            cur.execute("""
                SELECT table_name, latest_date, status, error_message
                FROM data_loader_status
                ORDER BY latest_date DESC
                LIMIT 10
            """)
            rows = cur.fetchall()
            if rows:
                for table_name, latest_date, status, error_msg in rows:
                    status_icon = "[OK]" if status == "success" else "[FAIL]"
                    print(f"{status_icon} {table_name:40s} | {latest_date} | {status}")
                    if error_msg:
                        print(f"  -> {error_msg[:80]}")
            else:
                print("No loader status entries found (table may be empty)")
    except Exception as e:
        print(f"Loader status check error: {e}")

def check_rds_connections():
    """Check current RDS configuration."""
    print("\n" + "="*70)
    print("RDS CONNECTION POOL")
    print("="*70)

    try:
        with DatabaseContext('read') as cur:
            # Check current max_connections setting
            cur.execute("SHOW max_connections")
            row = cur.fetchone()
            if row:
                print(f"[OK] RDS max_connections: {row[0]}")

            # Check current connections
            cur.execute("""
                SELECT count(*), state
                FROM pg_stat_activity
                GROUP BY state
                ORDER BY count(*) DESC
            """)
            rows = cur.fetchall()
            if rows:
                print("\nCurrent connection states:")
                for count, state in rows:
                    print(f"  {count:3d} connections in state: {state}")

            # Check statement_timeout
            cur.execute("SHOW statement_timeout")
            row = cur.fetchone()
            if row:
                print(f"\n[OK] Default statement_timeout: {row[0]}")
    except Exception as e:
        print(f"Connection pool check error: {e}")

def main():
    print("\n" + "#"*70)
    print("# PIPELINE DIAGNOSTIC REPORT")
    print(f"# {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("#"*70)

    check_migrations()
    check_schema()
    check_rds_connections()
    check_table_freshness()
    check_loader_status()

    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print("""
If you see [FAIL] on critical items, the pipeline may still be blocked:
  - Migration 015 not applied -> sector_ranking won't load
  - Table data is stale/empty -> orchestrator Phase 1 will halt
  - Connection pool issues -> loaders timeout waiting for DB

If all checks are [OK] but the pipeline still fails, check:
  - CloudWatch logs for specific loader error messages
  - Step Functions execution status (may still be running)
  - Individual ECS task logs for each loader
""")

if __name__ == '__main__':
    main()
