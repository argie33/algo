#!/usr/bin/env python3
"""Refresh stale data tables for local testing.

This script updates buy_sell_daily and market_exposure_daily with today's data
so that signal generation (Phase 7) can run without being blocked by stale dependencies.

USAGE:
    python3 scripts/refresh_stale_data_for_testing.py

This is a TEST-ONLY script for local development. Do not use in production.
"""

import sys

from utils.db.context import DatabaseContext


def refresh_data() -> None:
    """Refresh stale data tables for testing."""
    print("=" * 80)
    print("REFRESHING STALE DATA FOR LOCAL TESTING")
    print("=" * 80)
    print()

    try:
        with DatabaseContext("read") as cur:
            # Get the most recent date with price data (this is our "today" for testing)
            cur.execute("SELECT MAX(date) FROM price_daily")
            latest_price_date = cur.fetchone()[0]

        if not latest_price_date:
            print("ERROR: No price data in database - cannot refresh")
            sys.exit(1)

        print(f"Using test date: {latest_price_date} (latest price data available)")
        print()

        with DatabaseContext("write") as cur:
            # Step 1: Ensure market_exposure_daily has data for this date
            print("[1/2] Updating market_exposure_daily...")
            cur.execute(
                """
                INSERT INTO market_exposure_daily
                (date, regime, exposure_pct, is_entry_allowed, market_exposure_pct,
                 long_exposure_pct, short_exposure_pct, exposure_tier, updated_at)
                VALUES (%s, 'confirmed_uptrend', 75.0, TRUE, 75.0, 75.0, 0.0, 'high', NOW())
                ON CONFLICT (date) DO UPDATE SET
                  regime = 'confirmed_uptrend',
                  exposure_pct = 75.0,
                  is_entry_allowed = TRUE,
                  market_exposure_pct = 75.0,
                  long_exposure_pct = 75.0,
                  short_exposure_pct = 0.0,
                  exposure_tier = 'high',
                  updated_at = NOW()
                """,
                (latest_price_date,),
            )
            print("  [OK] market_exposure_daily updated")

            # Step 2: Create synthetic buy signals from stocks with prices
            # (needed for signal generation to have candidate signals)
            print("[2/2] Creating test signals from available stocks...")
            cur.execute(
                """
                DELETE FROM buy_sell_daily
                WHERE date = %s AND signal_type = 'BUY'
                """,
                (latest_price_date,),
            )

            cur.execute(
                """
                INSERT INTO buy_sell_daily
                (symbol, date, signal_type, entry_price, signal_strength, signal_quality_score, updated_at)
                SELECT
                    pd.symbol,
                    %s,
                    'BUY',
                    pd.close,
                    0.70,
                    COALESCE(ss.composite_score, 65.0) / 100.0,
                    NOW()
                FROM price_daily pd
                LEFT JOIN stock_scores ss ON pd.symbol = ss.symbol
                WHERE pd.date = %s
                ORDER BY COALESCE(ss.composite_score, 65.0) DESC
                LIMIT 30  -- Create 30 test signals
                ON CONFLICT (symbol, date) DO NOTHING
                """,
                (latest_price_date, latest_price_date),
            )
            inserted = cur.rowcount
            print(f"  [OK] Created {inserted} test BUY signals")

            # Verify the updates
            print()
            print("[VERIFICATION]")
            cur.execute("SELECT COUNT(*) FROM market_exposure_daily WHERE date = %s", (latest_price_date,))
            market_count = cur.fetchone()[0]
            print(f"  market_exposure_daily: {market_count} row(s)")

            cur.execute(
                "SELECT COUNT(*) FROM buy_sell_daily WHERE date = %s AND signal_type = 'BUY'",
                (latest_price_date,),
            )
            signal_count = cur.fetchone()[0]
            print(f"  buy_sell_daily (BUY signals): {signal_count} row(s)")

        print()
        print("=" * 80)
        print("SUCCESS: Test data refreshed")
        print("=" * 80)
        print()
        print("NEXT STEPS:")
        print(f"  Signals created for date: {latest_price_date}")
        print()
        print("  1. Run orchestrator (Phase 7 will generate trading signals):")
        print("     python3 scripts/trigger_orchestrator.py --run morning --mode paper")
        print()
        print("  2. Or run dashboard with local API:")
        print("     python3 api-pkg/dev_server.py &")
        print("     python3 -m dashboard --local")
        print()

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    refresh_data()
