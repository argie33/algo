#!/usr/bin/env python3
"""
Swing Trader Scores Loader - Computes swing trading quality scores.

Computes per-symbol swing scores with a 7-component breakdown by joining
signal_quality_scores, trend_template_data, and technical_data_daily.
The component breakdown maps directly to the RadarChart in SwingCandidates.jsx:
  setup        — Minervini 8-point template (% of 8 criteria met)
  trend        — Weinstein stage quality (Stage 2 = 100, Stage 1 = 50, other = 0)
  momentum     — RSI normalized to momentum sweet spot (40-70 RSI → 0-100)
  volume       — 20-day price ROC as volume-confirmation proxy
  fundamentals — overall composite_sqs (best available proxy without full fundamentals)
  sector       — overall composite_sqs (fallback; enriched by sector loader separately)
  multi_tf     — trend + momentum blend (confirms trend on multiple timeframes)

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
        """Compute swing trader scores with 7-component breakdown."""
        from algo.algo_market_calendar import MarketCalendar

        try:
            end = date.today()
            while end > date(2020, 1, 1) and not MarketCalendar.is_trading_day(end):
                end = end - timedelta(days=1)

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
                    # Join signal_quality_scores with trend + technical data for component breakdown
                    cur.execute("""
                        SELECT
                            sqs.symbol,
                            sqs.date,
                            COALESCE(sqs.composite_sqs, 0) AS composite_sqs,
                            COALESCE(td.minervini_trend_score, 0) AS minervini_score,
                            COALESCE(td.weinstein_stage, 0) AS weinstein_stage,
                            tdd.rsi,
                            tdd.roc_20d,
                            tdd.mansfield_rs
                        FROM signal_quality_scores sqs
                        LEFT JOIN trend_template_data td
                            ON td.symbol = sqs.symbol AND td.date = sqs.date
                        LEFT JOIN technical_data_daily tdd
                            ON tdd.symbol = sqs.symbol AND tdd.date = sqs.date
                        WHERE sqs.symbol = %s AND sqs.date >= %s AND sqs.date <= %s
                        ORDER BY sqs.date ASC
                    """, (symbol, start, end))
                    rows = cur.fetchall()

                    if not rows:
                        return None

                    all_scores = []
                    for row in rows:
                        score_row = self._compute_swing_score(row)
                        if score_row:
                            all_scores.append(score_row)

                    return all_scores if all_scores else None
            finally:
                conn.close()
        except Exception as e:
            logging.debug(f"Swing score computation error for {symbol}: {e}")
            return None

    def _compute_swing_score(self, row) -> Optional[Dict]:
        """Compute swing trader score with 7-component breakdown.

        Input columns: symbol, date, composite_sqs, minervini_score, weinstein_stage,
                       rsi, roc_20d, mansfield_rs
        """
        if not row:
            return None

        try:
            (symbol, score_date, composite_sqs,
             minervini_score, weinstein_stage,
             rsi, roc_20d, mansfield_rs) = row

            composite = float(composite_sqs or 0)

            # --- 7 component scores (0-100 each) ---

            # Setup: Minervini 8-point template completion (0-100)
            setup = min(100.0, float(minervini_score or 0) / 8.0 * 100.0)

            # Trend: Weinstein stage quality
            stage = int(weinstein_stage or 0)
            if stage == 2:
                trend = 100.0
            elif stage == 1:
                trend = 50.0
            elif stage == 3:
                trend = 25.0
            else:
                trend = 0.0

            # Momentum: RSI in the 40-70 sweet spot (below 40 = weak, above 70 = extended)
            rsi_f = float(rsi) if rsi is not None else 50.0
            if 40 <= rsi_f <= 70:
                momentum = (rsi_f - 40) / 30.0 * 100.0  # 0 at RSI=40, 100 at RSI=70
            elif rsi_f < 40:
                momentum = 0.0  # below sweet spot = weak
            else:  # > 70 (overbought)
                momentum = max(0.0, 100.0 - (rsi_f - 70) / 30.0 * 100.0)

            # Volume: 20-day ROC as proxy for sustained institutional participation
            roc = float(roc_20d) if roc_20d is not None else 0.0
            # >10% 20-day ROC = strong; negative = weak
            volume = max(0.0, min(100.0, 50.0 + roc * 2.5))

            # Fundamentals: use overall composite as best available proxy
            fundamentals = composite

            # Sector: Mansfield RS if available (positive RS = sector leadership)
            if mansfield_rs is not None:
                rs = float(mansfield_rs)
                # Mansfield RS: 0 = at par, positive = outperforming, negative = underperforming
                sector = max(0.0, min(100.0, 50.0 + rs * 5.0))
            else:
                sector = composite  # fallback

            # Multi-timeframe: blend of trend + momentum (confirming at multiple scales)
            multi_tf = (trend * 0.6 + momentum * 0.4)

            # --- Grade and gates ---
            if composite >= 85:
                grade = 'A+'
            elif composite >= 75:
                grade = 'A'
            elif composite >= 65:
                grade = 'B'
            elif composite >= 55:
                grade = 'C'
            elif composite >= 45:
                grade = 'D'
            else:
                grade = 'F'

            pass_gates = composite >= 75
            fail_reason = None if pass_gates else (
                'Low composite score' if composite < 45 else 'Below quality threshold'
            )

            return {
                'symbol': symbol,
                'date': score_date,
                'score': round(composite, 2),
                'components': json.dumps({
                    'grade': grade,
                    'composite_sqs': round(composite, 1),
                    'pass_gates': pass_gates,
                    'fail_reason': fail_reason,
                    # 7-component breakdown (displayed in SwingCandidates radar chart)
                    'setup': round(setup, 1),
                    'trend': round(trend, 1),
                    'momentum': round(momentum, 1),
                    'volume': round(volume, 1),
                    'fundamentals': round(fundamentals, 1),
                    'sector': round(sector, 1),
                    'multi_tf': round(multi_tf, 1),
                })
            }
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
