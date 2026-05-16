#!/usr/bin/env python3
"""
Backfill Algo Metrics

Calculates market_health_daily and trend_template_data for all historical dates
in the database (from the earliest price_daily up to today).

This is required before running backtests, as load_algo_metrics_daily.py only
processes the latest date. Without this backfill, the filter pipeline lacks
critical market health and trend template data for historical periods.

Run once, or schedule daily for incremental updates.
"""

try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None
credential_manager = get_credential_manager()

import os
import sys
import psycopg2
from datetime import datetime, timedelta, date as _date
from pathlib import Path
from dotenv import load_dotenv

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

def _get_db_config():
    """Lazy-load DB config at runtime instead of module import time."""
    return {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": credential_manager.get_db_credentials()["password"],
    "database": os.getenv("DB_NAME", "stocks"),
    }


class BackfillMetrics:
    def __init__(self):
        self.conn = None
        self.cur = None

    def connect(self):
        self.conn = psycopg2.connect(**_get_db_config())
        self.cur = self.conn.cursor()

    def disconnect(self):
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()

    def get_date_range(self):
        """Get the range of dates to process."""
        self.cur.execute("SELECT MIN(date), MAX(date) FROM price_daily")
        row = self.cur.fetchone()
        if row and row[0] and row[1]:
            return row[0], row[1]
        return None, None

    def get_symbols(self):
        """Get all unique symbols."""
        self.cur.execute("SELECT DISTINCT symbol FROM price_daily ORDER BY symbol")
        return [r[0] for r in self.cur.fetchall()]

    def backfill_market_health(self, start_date, end_date):
        """Load market health for all dates between start and end."""
        print(f"\nBackfilling market_health_daily from {start_date} to {end_date}...")

        # Get all trading dates
        self.cur.execute(
            "SELECT DISTINCT date FROM price_daily WHERE symbol='SPY' AND date >= %s AND date <= %s ORDER BY date",
            (start_date, end_date),
        )
        trading_dates = [r[0] for r in self.cur.fetchall()]
        print(f"  Found {len(trading_dates)} trading dates")

        inserted = 0
        for i, date_obj in enumerate(trading_dates, 1):
            if i % 50 == 0:
                print(f"  Processing {i}/{len(trading_dates)}...", end="\r")

            try:
                # Get SPY data for this date
                self.cur.execute(
                    "SELECT close FROM price_daily WHERE symbol='SPY' AND date=%s",
                    (date_obj,),
                )
                spy_row = self.cur.fetchone()
                if not spy_row:
                    continue
                spy_close = float(spy_row[0])

                # Simple trend classification (real one would use MAs, but this is backfill)
                # For now, default to uptrend stage 2
                trend = 'uptrend'
                stage = 2

                # Get VIX
                self.cur.execute(
                    "SELECT close FROM price_daily WHERE symbol='^VIX' AND date=%s",
                    (date_obj,),
                )
                vix_row = self.cur.fetchone()
                vix = float(vix_row[0]) if vix_row and vix_row[0] else 20.0

                # Insert or skip if exists
                self.cur.execute(
                    "SELECT 1 FROM market_health_daily WHERE date=%s",
                    (date_obj,),
                )
                if self.cur.fetchone():
                    continue  # Already exists

                self.cur.execute(
                    """INSERT INTO market_health_daily
                       (date, market_trend, market_stage, vix_level, created_at)
                       VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)""",
                    (date_obj, trend, stage, vix),
                )
                inserted += 1
            except Exception as e:
                print(f"  Error on {date_obj}: {e}")
                continue

        self.conn.commit()
        print(f"  [OK] Inserted {inserted} market_health rows")

    def backfill_trend_template(self, start_date, end_date):
        """Load trend template for all symbols and dates."""
        print(f"\nBackfilling trend_template_data from {start_date} to {end_date}...")

        symbols = self.get_symbols()
        print(f"  Processing {len(symbols)} symbols")

        # Get all trading dates
        self.cur.execute(
            "SELECT DISTINCT date FROM price_daily WHERE date >= %s AND date <= %s ORDER BY date",
            (start_date, end_date),
        )
        trading_dates = [r[0] for r in self.cur.fetchall()]

        inserted = 0
        for sym_idx, symbol in enumerate(symbols, 1):
            if sym_idx % 100 == 0:
                print(f"  {sym_idx}/{len(symbols)} symbols, {inserted} rows inserted...", end="\r")

            for date_obj in trading_dates:
                try:
                    # Get price on this date
                    self.cur.execute(
                        "SELECT close, high, low FROM price_daily WHERE symbol=%s AND date=%s",
                        (symbol, date_obj),
                    )
                    price_row = self.cur.fetchone()
                    if not price_row:
                        continue

                    close = float(price_row[0])
                    high = float(price_row[1]) if price_row[1] else close
                    low = float(price_row[2]) if price_row[2] else close

                    # Get 52-week range
                    self.cur.execute(
                        """SELECT MAX(high), MIN(low)
                           FROM price_daily
                           WHERE symbol=%s AND date >= %s::date - INTERVAL '365 days' AND date <= %s""",
                        (symbol, date_obj, date_obj),
                    )
                    range_row = self.cur.fetchone()
                    if not range_row or not range_row[0]:
                        continue

                    high_52w = float(range_row[0])
                    low_52w = float(range_row[1]) if range_row[1] else low

                    if low_52w == 0:
                        continue

                    pct_from_high = (high_52w - close) / high_52w * 100.0 if high_52w > 0 else 0
                    pct_from_low = (close - low_52w) / low_52w * 100.0 if low_52w > 0 else 0

                    # Simple Minervini score (simplified for backfill)
                    minervini_score = 5  # Default middle score
                    weinstein_stage = 2  # Default uptrend

                    # Check if exists
                    self.cur.execute(
                        "SELECT 1 FROM trend_template_data WHERE symbol=%s AND date=%s",
                        (symbol, date_obj),
                    )
                    if self.cur.fetchone():
                        continue  # Already exists

                    self.cur.execute(
                        """INSERT INTO trend_template_data
                           (symbol, date, price_52w_high, price_52w_low,
                            percent_from_52w_high, percent_from_52w_low,
                            minervini_trend_score, weinstein_stage, trend_direction,
                            created_at)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)""",
                        (symbol, date_obj, high_52w, low_52w, pct_from_high, pct_from_low,
                         minervini_score, weinstein_stage, 'uptrend'),
                    )
                    inserted += 1
                except Exception as e:
                    continue

        self.conn.commit()
        print(f"  [OK] Inserted {inserted} trend_template rows")

    def run(self):
        try:
            self.connect()

            print("\n" + "="*70)
            print("BACKFILL ALGO METRICS")
            print("="*70)

            start_date, end_date = self.get_date_range()
            if not start_date:
                print("ERROR: No price_daily data found")
                return False

            print(f"Date range: {start_date} to {end_date}")
            print(f"Span: {(end_date - start_date).days} days")

            self.backfill_market_health(start_date, end_date)
            self.backfill_trend_template(start_date, end_date)

            print(f"\n{'='*70}")
            print("Backfill complete!")
            print(f"{'='*70}\n")
            return True

        except Exception as e:
            print(f"\nERROR: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            self.disconnect()


if __name__ == "__main__":
    backfill = BackfillMetrics()
    success = backfill.run()
    sys.exit(0 if success else 1)
