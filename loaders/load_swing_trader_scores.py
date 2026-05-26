#!/usr/bin/env python3
"""
Swing Trader Scores Loader - Computes swing trading quality scores.

FIX (May 25): Now pulls from signal_quality_scores which has real data,
instead of buy_sell_daily which has NULL/zero quality metrics.

Inherits from OptimalLoader: watermarks, dedup, parallelism, bulk COPY.

Run:
    python3 loaders/load_swing_trader_scores.py [--parallelism 8]
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.structured_logger import get_logger
import argparse
import logging
logger = get_logger(__name__)
import os
from utils.loader_helpers import get_active_symbols
from config.env_loader import load_env
from datetime import date, timedelta
from typing import List, Optional, Dict
import json

from utils.optimal_loader import OptimalLoader
from utils.db_connection import get_db_connection


class SwingTraderScoresLoader(OptimalLoader):
    table_name = "swing_trader_scores"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Compute swing trader scores from signal_quality_scores."""
        from algo.algo_market_calendar import MarketCalendar

        try:
            end = date.today()
            # If today is not a trading day, use yesterday instead
            # (prevents computing scores for non-trading days when no new signals exist)
            while end > date(2020, 1, 1) and not MarketCalendar.is_trading_day(end):
                end = end - timedelta(days=1)

            # On ECS restart the in-memory watermark is empty, so since=None.
            # Read the actual DB max date to avoid re-querying 5 years of history.
            if since is None:
                try:
                    wm_conn = get_db_connection()
                    with wm_conn.cursor() as wm_cur:
                        wm_cur.execute(
                            "SELECT MAX(date) FROM swing_trader_scores WHERE symbol = %s",
                            (symbol,),
                        )
                        wm_row = wm_cur.fetchone()
                    wm_conn.close()
                    if wm_row and wm_row[0]:
                        since = wm_row[0] if isinstance(wm_row[0], date) else date.fromisoformat(str(wm_row[0]))
                except Exception as e:
                    logging.warning(f"Could not read swing_trader_scores watermark for {symbol}: {e}")

            if since is None:
                start = end - timedelta(days=5 * 365)
            else:
                start = since + timedelta(days=1) if isinstance(since, date) else date.fromisoformat(str(since).split('T')[0]) + timedelta(days=1)

            if start >= end:
                return None

            conn = get_db_connection()
            try:
                with conn.cursor() as cur:
                    # Get signal quality scores for this symbol
                    # signal_quality_scores table has composite_sqs (0-100 scale)
                    # Note: Only composite_sqs is populated by load_signal_quality_scores
                    cur.execute("""
                        SELECT symbol, date, COALESCE(composite_sqs, 0) as composite_sqs
                        FROM signal_quality_scores
                        WHERE symbol = %s AND date >= %s AND date <= %s
                        ORDER BY date ASC
                    """, (symbol, start, end))
                    rows = cur.fetchall()

                    if not rows:
                        return None

                    # Compute swing scores for all dates
                    all_scores = []
                    for row in rows:
                        scores = self._compute_swing_score(symbol, row)
                        if scores:
                            all_scores.extend(scores)

                    return all_scores if all_scores else None
            finally:
                conn.close()
        except Exception as e:
            logging.debug(f"Swing score computation error for {symbol}: {e}")
            return None

    def _compute_swing_score(self, symbol: str, signal_data: tuple) -> Optional[List[Dict]]:
        """Compute swing trader score from signal quality scores.

        Input: (symbol, date, composite_sqs)
        composite_sqs is already 0-100 scale from load_signal_quality_scores.
        """
        if not signal_data:
            return None

        try:
            # Unpack 3 columns: symbol, date, composite_sqs
            symbol, date, composite_sqs = signal_data

            # composite_sqs is already 0-100 score
            composite_score = float(composite_sqs or 0)

            # Determine grade based on composite score
            if composite_score >= 85:
                grade = 'A+'
            elif composite_score >= 75:
                grade = 'A'
            elif composite_score >= 65:
                grade = 'B'
            elif composite_score >= 55:
                grade = 'C'
            elif composite_score >= 45:
                grade = 'D'
            else:
                grade = 'F'

            pass_gates = composite_score >= 75
            fail_reason = None if pass_gates else (
                'Low composite score' if composite_score < 45 else
                'Below quality threshold'
            )
            return [{
                'symbol': symbol,
                'date': date,
                'score': round(composite_score, 2),
                'components': json.dumps({
                    'grade': grade,
                    'composite_sqs': round(composite_score, 1),
                    'pass_gates': pass_gates,
                    'fail_reason': fail_reason,
                })
            }]
        except Exception as e:
            logging.debug(f"Score computation failed: {e}")
            return None

    def transform(self, rows):
        """Rows are clean."""
        return rows

    def _validate_row(self, row: dict) -> bool:
        """Validate swing score row."""
        if not super()._validate_row(row):
            return False
        return (
            row.get('symbol') is not None and
            row.get('date') is not None and
            row.get('score') is not None and
            0 <= float(row.get('score', 0)) <= 100
        )


def main():
    load_env()
    parser = argparse.ArgumentParser(description="Swing Trader Scores Loader")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols")
    parser.add_argument("--parallelism", type=int, default=8, help="Concurrent workers")
    args = parser.parse_args()

    symbols = args.symbols.split(",") if args.symbols else get_active_symbols(timeout_secs=60)
    loader = SwingTraderScoresLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    fail_rate = stats.get("symbols_failed", 0) / max(len(symbols), 1)
    if fail_rate > 0.05:
        logger.error(f"Too many failures: {stats['symbols_failed']}/{len(symbols)} ({fail_rate*100:.1f}%)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
