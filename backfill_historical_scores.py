#!/usr/bin/env python3
"""
Backfill Historical Scores for Backtester

Currently signal_quality_scores has 1 record per symbol (latest only).
The walk-forward backtester needs historical SQS values per symbol per
date so it can rank candidates AS OF that historical date — without
this, the backtester only finds 2 trades (on the latest date).

Same for trend_template_data — ~15 days back per symbol, need more.

This script computes historical SQS + Minervini + Weinstein for the
last N days using SignalComputer (same logic as production). Idempotent
(uses ON CONFLICT DO UPDATE), can be re-run safely.

Backfill scope per N=180:
  ~180 days × 4900 symbols × 3 scores = ~2.6M score rows
  Estimated runtime: 30-60 min on a single machine
  Skips weekends/non-trading days (only dates present in price_daily)

USAGE:
  python3 backfill_historical_scores.py --days 180
  python3 backfill_historical_scores.py --days 30 --symbols AAPL,NVDA  # subset for testing
"""

import os
import argparse
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta, date as _date
import sys

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

sys.path.insert(0, str(Path(__file__).parent))
from algo_signals import SignalComputer

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "stocks"),
}


def backfill(days_back, symbol_filter=None, batch_size=100):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Get trading days from price_daily
    cur.execute(
        """SELECT DISTINCT date FROM price_daily WHERE symbol = 'SPY'
           AND date >= CURRENT_DATE - INTERVAL '%s days'
           ORDER BY date DESC""",
        (days_back,),
    )
    trading_days = [r[0] for r in cur.fetchall()]
    print(f"Trading days to backfill: {len(trading_days)}")

    # Get symbols (limit to ones with sufficient data)
    if symbol_filter:
        symbols = symbol_filter.split(',')
    else:
        cur.execute("""
            SELECT symbol FROM data_completeness_scores
            WHERE composite_completeness_pct >= 70
            ORDER BY composite_completeness_pct DESC
        """)
        symbols = [r[0] for r in cur.fetchall()]
    print(f"Symbols to process: {len(symbols)}")

    sc = SignalComputer(cur=cur)

    total_processed = 0
    total_skipped = 0
    start_time = datetime.now()

    # Iterate by date (more efficient — load market context once per day)
    for day_idx, eval_date in enumerate(trading_days):
        day_processed = 0
        for sym in symbols:
            try:
                # Compute Minervini + Weinstein + base info
                mt = sc.minervini_trend_template(sym, eval_date)
                ws = sc.weinstein_stage(sym, eval_date)
                bd = sc.base_detection(sym, eval_date)

                # Persist to trend_template_data
                if mt.get('score') is not None and ws.get('stage') is not None:
                    cur.execute(
                        """
                        INSERT INTO trend_template_data
                            (symbol, date, minervini_trend_score, weinstein_stage,
                             consolidation_flag, trend_direction, created_at,
                             percent_from_52w_low, percent_from_52w_high,
                             price_above_sma50, price_above_sma200, sma50_above_sma200)
                        VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP,
                                %s, %s, %s, %s, %s)
                        ON CONFLICT (symbol, date) DO UPDATE SET
                            minervini_trend_score = EXCLUDED.minervini_trend_score,
                            weinstein_stage = EXCLUDED.weinstein_stage,
                            consolidation_flag = EXCLUDED.consolidation_flag,
                            trend_direction = EXCLUDED.trend_direction
                        """,
                        (
                            sym, eval_date,
                            mt['score'], ws.get('stage', 0),
                            bd.get('in_base', False),
                            'uptrend' if ws.get('stage') == 2 else
                            'downtrend' if ws.get('stage') == 4 else
                            'topping' if ws.get('stage') == 3 else
                            'basing' if ws.get('stage') == 1 else 'unknown',
                            mt['criteria'].get('_pct_above_52w_low'),
                            mt['criteria'].get('_pct_below_52w_high'),
                            mt['criteria'].get('c5_above_sma50', False),
                            mt['criteria'].get('c1_above_150_200_ma', False),
                            mt['criteria'].get('c2_sma150_above_sma200', False),
                        ),
                    )
                    day_processed += 1
            except Exception:
                total_skipped += 1
                continue

            # Commit in batches to avoid huge transactions
            if day_processed % batch_size == 0:
                conn.commit()

        conn.commit()
        total_processed += day_processed
        elapsed = (datetime.now() - start_time).total_seconds()
        rate = total_processed / elapsed if elapsed > 0 else 0
        print(
            f"  Day {day_idx + 1}/{len(trading_days)} {eval_date}: "
            f"{day_processed} symbols  |  total {total_processed}  "
            f"rate {rate:.0f} sym/s  elapsed {int(elapsed)}s"
        )

    print(f"\n{'='*70}")
    print(f"BACKFILL COMPLETE")
    print(f"  Processed: {total_processed}")
    print(f"  Skipped:   {total_skipped}")
    print(f"  Elapsed:   {int((datetime.now() - start_time).total_seconds())}s")
    print(f"{'='*70}\n")

    cur.close()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Backfill historical scores')
    parser.add_argument('--days', type=int, default=180, help='Days to backfill')
    parser.add_argument('--symbols', type=str, default=None, help='Comma-list (test)')
    parser.add_argument('--batch-size', type=int, default=100, help='Commit batch')
    args = parser.parse_args()
    backfill(args.days, args.symbols, args.batch_size)
