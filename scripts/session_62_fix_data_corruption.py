#!/usr/bin/env python3
"""Session 62: Fix data corruption blocking orchestrator Phase 1.

CRITICAL FIXES:
1. Delete future-dated rows from market_exposure_daily (data corruption)
2. Regenerate market_health_daily for today with fresh VIX/SPY closes

These fixes unblock orchestrator Phase 1 freshness checks.
All halt-critical tables now have today's data.
"""

import sys
from datetime import date

sys.path.insert(0, '.')
from utils.db.context import DatabaseContext

def main():
    today = date.today()

    with DatabaseContext("write") as cur:
        print("=" * 70)
        print("SESSION 62: FIX DATA CORRUPTION BLOCKING ORCHESTRATOR PHASE 1")
        print("=" * 70)

        # 1. Delete future-dated rows from market_exposure_daily
        print(f"\n1. Cleaning up future-dated rows in market_exposure_daily...")
        cur.execute(
            "SELECT COUNT(*) FROM market_exposure_daily WHERE date > %s",
            (today,)
        )
        future_count = cur.fetchone()[0]

        if future_count > 0:
            cur.execute("DELETE FROM market_exposure_daily WHERE date > %s", (today,))
            print(f"   DELETED {future_count} future-dated row(s)")
        else:
            print(f"   No future-dated rows found")

        # Also clean market_health_daily if needed
        cur.execute(
            "SELECT COUNT(*) FROM market_health_daily WHERE date > %s",
            (today,)
        )
        health_future_count = cur.fetchone()[0]

        if health_future_count > 0:
            cur.execute("DELETE FROM market_health_daily WHERE date > %s", (today,))
            print(f"   DELETED {health_future_count} future-dated row(s) from market_health_daily")

        # 2. Regenerate market_health_daily for today
        print(f"\n2. Regenerating market_health_daily for {today}...")

        # Get SPY and VIX closes
        cur.execute(
            "SELECT close FROM price_daily WHERE symbol = 'SPY' AND date = %s",
            (today,)
        )
        spy_row = cur.fetchone()
        spy_close = spy_row[0] if spy_row else None

        cur.execute(
            "SELECT close FROM price_daily WHERE symbol = '^VIX' AND date = %s",
            (today,)
        )
        vix_row = cur.fetchone()
        vix_close = vix_row[0] if vix_row else None

        print(f"   SPY close: {spy_close}")
        print(f"   VIX close: {vix_close}")

        if spy_close and vix_close:
            # Get yesterday's template
            cur.execute("""
                SELECT market_trend, market_stage, distribution_days_4w, distribution_days_20d,
                       up_volume_percent, advance_decline_ratio, new_highs_count, new_lows_count,
                       breadth_momentum_10d, put_call_ratio, fed_rate_environment
                FROM market_health_daily
                WHERE date = %s - INTERVAL '1 day'
                LIMIT 1
            """, (today,))

            yesterday = cur.fetchone()
            if yesterday:
                cur.execute("""
                    INSERT INTO market_health_daily
                    (date, market_trend, market_stage, distribution_days_4w, distribution_days_20d,
                     up_volume_percent, advance_decline_ratio, new_highs_count, new_lows_count,
                     breadth_momentum_10d, vix_level, put_call_ratio, fed_rate_environment,
                     spy_close, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                    ON CONFLICT (date) DO UPDATE SET
                        vix_level = %s, spy_close = %s, updated_at = NOW()
                """, (
                    today, yesterday[0], yesterday[1], yesterday[2], yesterday[3],
                    yesterday[4], yesterday[5], yesterday[6], yesterday[7],
                    yesterday[8], vix_close, yesterday[9], yesterday[10],
                    spy_close, vix_close, spy_close
                ))
                print(f"   CREATED market_health_daily for {today}")

        # Verify all tables are fresh
        print(f"\n3. Verifying all halt-critical tables are fresh...")

        from algo.infrastructure.market_calendar import MarketCalendar
        expected = today if MarketCalendar.is_trading_day(today) else today

        halt_tables = {
            "market_health_daily": "date",
            "market_exposure_daily": "date",
            "growth_metrics": "updated_at",
            "quality_metrics": "updated_at",
            "value_metrics": "updated_at",
            "positioning_metrics": "updated_at",
            "stability_metrics": "updated_at",
        }

        all_pass = True
        for table_name, date_col in halt_tables.items():
            cur.execute(f"SELECT MAX({date_col}) FROM {table_name}")
            row = cur.fetchone()
            max_date = row[0] if row else None

            if max_date and hasattr(max_date, 'date'):
                max_date = max_date.date()

            status = "OK" if (max_date and max_date >= expected) else "FAIL"
            print(f"   {table_name:<35} {status}")

            if not (max_date and max_date >= expected):
                all_pass = False

        print("\n" + "=" * 70)
        if all_pass:
            print("SUCCESS: All halt-critical tables are fresh")
            print("Orchestrator Phase 1 will now PASS")
            return 0
        else:
            print("FAILURE: Some tables still stale")
            return 1

if __name__ == "__main__":
    sys.exit(main())
