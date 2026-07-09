#!/usr/bin/env python3
"""Fix data loader status tracking issues.

PROBLEM: Several loaders are stuck in RUNNING state for >2 hours with message
"Stuck in RUNNING for >2hrs with no active ECS task" even though they've completed.

This indicates the loader completion logic isn't updating the status properly.

SOLUTION: This script:
1. Identifies loaders stuck in RUNNING state with no active ECS tasks
2. Cleans up stale status entries
3. Marks them as FAILED or resets to allow retry
4. Logs findings for operator review
"""

import sys
from datetime import datetime, timedelta

import psycopg2

sys.path.insert(0, '.')
from utils.db.context import DatabaseContext

logger_name = "fix_data_loader_status"


def fix_loader_status():
    """Clean up stuck loader status entries."""
    with DatabaseContext("write") as cur:
        # Get stale loader status entries
        cur.execute("""
            SELECT table_name, status, last_updated, reason
            FROM data_loader_status
            WHERE reason LIKE '%Stuck in RUNNING%'
            AND last_updated < NOW() - INTERVAL '2 hours'
            ORDER BY last_updated DESC
        """)

        stuck_loaders = cur.fetchall()

        print(f"\n[FIX_LOADER_STATUS] Found {len(stuck_loaders)} stuck loaders:")

        fixed_count = 0
        for table_name, status, last_updated, reason in stuck_loaders:
            print(f"\n  {table_name}:")
            print(f"    Status: {status}")
            print(f"    Last updated: {last_updated}")
            print(f"    Age: {datetime.now() - last_updated}")

            # Update the status to mark as stale
            # Don't force FAILED - just clear the stuck reason so next run can retry
            if status == 'COMPLETED':
                # Loader was stuck but marked completed - leave it as-is
                new_status = status
                new_reason = "Previously stuck but marked completed"
            else:
                # Loader was stuck in RUNNING/FAILED - mark as needs retry
                new_status = 'IDLE'
                new_reason = 'Reset after stuck detection'

            try:
                cur.execute("""
                    UPDATE data_loader_status
                    SET status = %s, reason = %s, last_updated = NOW()
                    WHERE table_name = %s
                """, (new_status, new_reason, table_name))
                fixed_count += 1
                print(f"    FIXED: {status} -> {new_status}")
            except Exception as e:
                print(f"    ERROR updating: {e}")

        # Commit changes
        cur.connection.commit()

        print(f"\n[FIX_LOADER_STATUS] Fixed {fixed_count}/{len(stuck_loaders)} stuck loaders")
        return fixed_count


def check_data_freshness():
    """Check data freshness across all critical tables."""
    with DatabaseContext("read") as cur:
        print(f"\n[DATA_FRESHNESS_CHECK]")

        tables_to_check = [
            ("price_daily", "date"),
            ("technical_data_daily", "date"),
            ("stock_scores", "updated_at"),
            ("market_exposure_daily", "date"),
            ("buy_sell_daily", "date"),
        ]

        for table_name, date_col in tables_to_check:
            cur.execute(f"""
                SELECT MAX({date_col}) as latest, COUNT(*) as cnt
                FROM {table_name}
            """)
            latest_date, count = cur.fetchone()

            if latest_date:
                age = datetime.now() - (latest_date if isinstance(latest_date, datetime) else datetime.combine(latest_date, datetime.min.time()))
                freshness = "FRESH" if age.days == 0 else f"STALE ({age.days}d old)"
            else:
                freshness = "EMPTY"

            print(f"  {table_name:30} {freshness:20} ({count} records)")


if __name__ == "__main__":
    try:
        fix_loader_status()
        check_data_freshness()
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
