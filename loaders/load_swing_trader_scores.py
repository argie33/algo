#!/usr/bin/env python3
"""
Swing Trader Scores Loader - Computes swing trading quality scores.

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
        """Compute swing trader scores from buy_sell_daily signals."""
        try:
            end = date.today()
            if since is None:
                start = end - timedelta(days=5 * 365)  # 5 years initial load
            else:
                start = since + timedelta(days=1) if isinstance(since, date) else date.fromisoformat(str(since).split('T')[0]) + timedelta(days=1)

            if start >= end:
                return None

            conn = get_db_connection()
            try:
                with conn.cursor() as cur:
                    # Get ALL buy/sell signals for this symbol (not just most recent)
                    cur.execute("""
                        SELECT
                            symbol, date, signal, strength, reason,
                            entry_quality_score, signal_quality_score,
                            risk_reward_ratio, volume_surge_pct
                        FROM buy_sell_daily
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
        """Compute swing trader score from signal data."""
        if not signal_data:
            return None

        try:
            symbol, date, signal, strength, reason, entry_q, signal_q, r_r, vol_surge = signal_data

            # Normalize components to 0-100 scale
            signal_quality = float(signal_q or 0)  # Already 0-100
            entry_quality = float(entry_q or 0)    # Already 0-100
            risk_reward = min(100, float(r_r or 0) * 10)  # Scale RR ratio to 0-100
            volume_component = min(100, float(vol_surge or 0))  # Volume surge %

            # Composite swing score (0-100)
            weights = {
                'signal_quality': 0.35,
                'entry_quality': 0.30,
                'risk_reward': 0.20,
                'volume': 0.15
            }

            composite_score = (
                signal_quality * weights['signal_quality'] +
                entry_quality * weights['entry_quality'] +
                risk_reward * weights['risk_reward'] +
                volume_component * weights['volume']
            )

            # Determine grade
            if composite_score >= 80:
                grade = 'A'
            elif composite_score >= 70:
                grade = 'B'
            elif composite_score >= 60:
                grade = 'C'
            elif composite_score >= 50:
                grade = 'D'
            else:
                grade = 'F'

            return [{
                'symbol': symbol,
                'date': date,
                'score': round(composite_score, 2),
                'components': json.dumps({
                    'grade': grade,
                    'signal_quality': round(signal_quality, 1),
                    'entry_quality': round(entry_quality, 1),
                    'risk_reward': round(risk_reward, 1),
                    'volume': round(volume_component, 1),
                    'reason': reason
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

    symbols = args.symbols.split(",") if args.symbols else get_active_symbols()
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
