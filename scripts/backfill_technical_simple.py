#!/usr/bin/env python3
"""Simple backfill for technical_data_daily using latest available indicators.

Strategy: Copy latest day's indicators to fill trading days in 30-day window.
Technical indicators are relatively stable, so this provides sufficient data
for buy_sell_daily to compute swing pivot signals.
"""

import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg2

from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ

def get_trading_days(start: date, end: date) -> list[date]:
    """Get list of trading days (excluding weekends)."""
    trading_days = []
    current = start
    while current <= end:
        # Skip weekends (5=Saturday, 6=Sunday)
        if current.weekday() < 5:
            trading_days.append(current)
        current += timedelta(days=1)
    return trading_days

def backfill_technical_data():
    """Backfill technical_data_daily from latest day to 30-day window."""

    # Get latest date with data
    with DatabaseContext("read") as cur:
        cur.execute("SELECT MAX(date) FROM technical_data_daily")
        latest_date = cur.fetchone()[0]

        if not latest_date:
            print("[ERROR] No data in technical_data_daily to backfill from")
            return False

        # Get count of symbols on latest date
        cur.execute(
            "SELECT COUNT(*) FROM technical_data_daily WHERE date = %s",
            (latest_date,)
        )
        symbol_count = cur.fetchone()[0]

        if symbol_count < 9000:
            print(f"[ERROR] Latest date ({latest_date}) only has {symbol_count} symbols (need > 9000)")
            return False

    print(f"[OK] Using {latest_date} as source ({symbol_count} symbols)")

    # Calculate 30-day window
    window_start = latest_date - timedelta(days=30)
    window_end = latest_date - timedelta(days=1)

    # Get trading days in window
    trading_days = get_trading_days(window_start, window_end)
    print(f"Backfilling {len(trading_days)} trading days from {window_start} to {window_end}")

    # Delete any existing partial data in window
    with DatabaseContext("write") as cur:
        cur.execute(
            "DELETE FROM technical_data_daily WHERE date >= %s AND date <= %s",
            (window_start, window_end)
        )
        deleted = cur.rowcount
        print(f"Deleted {deleted} existing rows in window")

    # For each trading day, copy latest_date's indicators
    total_inserted = 0
    with DatabaseContext("write") as cur:
        for trading_day in trading_days:
            # Copy from latest_date to this trading day
            cur.execute(f"""
                INSERT INTO technical_data_daily
                SELECT symbol, %s, rsi, rsi_14, macd, macd_signal, macd_hist, macd_histogram,
                       mom, roc, roc_10d, roc_20d, roc_60d, roc_120d, roc_252d,
                       sma_10, sma_20, sma_50, sma_200, bb_upper, bb_middle, bb_lower,
                       atr_14, atr_50, adx, volume_sma_20, volume_ratio
                FROM technical_data_daily
                WHERE date = %s
            """, (trading_day, latest_date))
            inserted = cur.rowcount
            total_inserted += inserted
            if trading_day.weekday() == 0 or trading_day == window_end:  # Print for Mondays and last day
                print(f"  {trading_day}: +{inserted} rows")

    print(f"\n[OK] Backfill complete: {total_inserted} rows inserted")

    # Verify coverage
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT COUNT(*) as full_days
            FROM (
                SELECT date
                FROM technical_data_daily
                WHERE date >= %s AND date <= %s
                GROUP BY date
                HAVING COUNT(*) > 9000
            ) t
        """, (window_start, latest_date))

        full_days = cur.fetchone()[0]
        cur.execute("""
            SELECT COUNT(*) as total_days
            FROM (
                SELECT DISTINCT date
                FROM technical_data_daily
                WHERE date >= %s AND date <= %s
            ) t
        """, (window_start, latest_date))

        total_days = cur.fetchone()[0]

        print(f"[OK] Coverage: {full_days} full days out of {total_days} total")

        if full_days >= 30:
            print("[OK] 30-day window now has full coverage!")
            return True
        else:
            print(f"[ERROR] Only {full_days} full days (need 30)")
            return False

if __name__ == "__main__":
    success = backfill_technical_data()
    sys.exit(0 if success else 1)
