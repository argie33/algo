#!/usr/bin/env python3
"""Check market_health_daily data availability."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils.db import DatabaseContext
from utils.infrastructure import EASTERN_TZ


def check_market_health():
    """Check market_health_daily table status."""
    print("\n" + "="*80)
    print("CHECKING MARKET_HEALTH_DAILY DATA")
    print("="*80 + "\n")

    try:
        with DatabaseContext("read") as cur:
            # 1. Check table structure
            print("1. TABLE STRUCTURE")
            print("-" * 80)

            cur.execute(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'market_health_daily'
                ORDER BY ordinal_position
                """
            )

            columns = cur.fetchall()
            print(f"Found {len(columns)} columns:\n")
            for col_name, data_type in columns:
                print(f"  {col_name:40s} {data_type}")

            # 2. Check data presence and freshness
            print("\n2. DATA FRESHNESS")
            print("-" * 80)

            cur.execute(
                """
                SELECT COUNT(*) as total_rows,
                       MAX(date) as latest_date,
                       MAX(updated_at) as latest_update
                FROM market_health_daily
                """
            )

            result = cur.fetchone()
            if result:
                total_rows, latest_date, latest_update = result
                print(f"Total rows: {total_rows}")
                print(f"Latest date: {latest_date}")
                print(f"Latest update: {latest_update}")

                if latest_update:
                    age = datetime.now(timezone.utc) - latest_update.replace(tzinfo=timezone.utc)
                    age_hours = age.total_seconds() / 3600
                    print(f"Data age: {age_hours:.1f} hours")

            # 3. Check data_unavailable flags
            print("\n3. DATA_UNAVAILABLE FLAGS")
            print("-" * 80)

            cur.execute(
                """
                SELECT
                    data_unavailable,
                    COUNT(*) as count,
                    reason
                FROM market_health_daily
                GROUP BY data_unavailable, reason
                ORDER BY count DESC
                """
            )

            flags = cur.fetchall()
            for unavailable, count, reason in flags:
                status = "UNAVAILABLE" if unavailable else "AVAILABLE"
                print(f"  {status:15s}: {count} rows, reason={reason}")

            # 4. Check recent data
            print("\n4. RECENT DATA SAMPLE")
            print("-" * 80)

            cur.execute(
                """
                SELECT date, updated_at, market_stage, distribution_days, market_health_score, data_unavailable, reason
                FROM market_health_daily
                ORDER BY date DESC
                LIMIT 5
                """
            )

            recent = cur.fetchall()
            for date, updated_at, stage, dist_days, health_score, unavailable, reason in recent:
                status = "UNAVAIL" if unavailable else "OK"
                print(f"  [{date}] {status:10s} stage={stage} dist_days={dist_days} health={health_score}")
                if reason:
                    print(f"    Reason: {reason}")

            # 5. Check loader status
            print("\n5. LOADER STATUS")
            print("-" * 80)

            cur.execute(
                """
                SELECT table_name, status, completion_pct, last_updated, symbols_loaded
                FROM data_loader_status
                WHERE table_name = 'market_health_daily'
                ORDER BY last_updated DESC
                LIMIT 1
                """
            )

            loader = cur.fetchone()
            if loader:
                table_name, status, completion, last_updated, symbols = loader
                print(f"Table: {table_name}")
                print(f"Status: {status}")
                print(f"Completion: {completion}%")
                print(f"Last updated: {last_updated}")
                print(f"Symbols loaded: {symbols}")
            else:
                print("⚠️ No loader status found for market_health_daily!")

            # 6. Check if there's a specific issue with today's data
            print("\n6. TODAY'S DATA STATUS")
            print("-" * 80)

            from datetime import date
            today = date.today()

            cur.execute(
                """
                SELECT COUNT(*), data_unavailable, reason
                FROM market_health_daily
                WHERE date = %s
                GROUP BY data_unavailable, reason
                """,
                (today,),
            )

            today_data = cur.fetchall()
            if today_data:
                print(f"Data for {today}:\n")
                for count, unavailable, reason in today_data:
                    status = "UNAVAIL" if unavailable else "OK"
                    print(f"  {status:10s}: {count} rows, reason={reason}")
            else:
                print(f"⚠️ No data for {today}!")

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(check_market_health())
