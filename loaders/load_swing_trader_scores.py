#!/usr/bin/env python3
"""
Swing Trader Scores Loader - Computes swing trading quality scores.

Computes per-symbol swing scores with a 7-component breakdown by joining
signal_quality_scores, trend_template_data, and technical_data_daily.
The component breakdown maps directly to the RadarChart in SwingCandidates.jsx:
  setup        â€" Minervini 8-point template (% of 8 criteria met)
  trend        â€" Weinstein stage quality (Stage 2 = 100, Stage 1 = 50, other = 0)
  momentum     â€" RSI normalized to momentum sweet spot (40-70 RSI â†' 0-100)
  volume       â€" 20-day price ROC as volume-confirmation proxy
  fundamentals â€" overall composite_sqs (best available proxy without full fundamentals)
  sector       â€" overall composite_sqs (fallback; enriched by sector loader separately)
  multi_tf     â€" trend + momentum blend (confirms trend on multiple timeframes)

Inherits from OptimalLoader: watermarks, dedup, parallelism, bulk COPY.

Run:
    python3 loaders/load_swing_trader_scores.py [--parallelism 8]
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
import argparse
logger = logging.getLogger(__name__)
import os
import psycopg2.sql
from utils.loader_helpers import get_active_symbols
from utils.timezone_utils import EASTERN_TZ
from datetime import date, timedelta
from typing import List, Optional, Dict
import json

from algo.algo_sql_safety import assert_safe_table
from utils.optimal_loader import OptimalLoader
from utils.timezone_utils import EASTERN_TZ
from utils.database_context import DatabaseContext
from utils.timezone_utils import EASTERN_TZ
from utils.loader_config import get_parallelism, get_default_parallelism
from utils.timezone_utils import EASTERN_TZ
from utils.grade_classifier import GradeClassifier
from utils.timezone_utils import EASTERN_TZ

class SwingTraderScoresLoader(OptimalLoader):
    table_name = "swing_trader_scores"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Compute swing trader scores with 7-component breakdown.

        FIX #5: Validates all 4 source tables before computing scores.
        """
        from algo.algo_market_calendar import MarketCalendar
        from datetime import datetime, timezone, timedelta as td
        from zoneinfo import ZoneInfo

        try:
            # CRITICAL: Use ET (trading hours), not UTC, to determine end date.
            # At 9 PM ET on June 4, UTC is already June 5. Use ET for correct trading day.
            # FIXED: Use ZoneInfo instead of hardcoded -5 offset to handle EDT properly.
            now_utc = datetime.now(timezone.utc)
            now_et = now_utc.astimezone(EASTERN_TZ)
            end = now_et.date()

            while end > date(2020, 1, 1) and not MarketCalendar.is_trading_day(end):
                end = end - timedelta(days=1)

            # Fall back to last date with signal_quality_scores if today's data isn't available yet
            # (e.g., morning prep runs before today's EOD data has been computed)
            try:
                with DatabaseContext('read') as fbc:
                    fbc.execute(
                        "SELECT MAX(date) FROM signal_quality_scores WHERE date <= %s",
                        (end,)
                    )
                    fb_row = fbc.fetchone()
                    last_sqs_date = fb_row[0] if fb_row and fb_row[0] else None
                    if last_sqs_date:
                        last_sqs = last_sqs_date if isinstance(last_sqs_date, date) else date.fromisoformat(str(last_sqs_date))
                        if last_sqs < end:
                            logging.info(
                                f"signal_quality_scores data up to {last_sqs}, not yet {end}. "
                                f"Using {last_sqs} as effective end date."
                            )
                            end = last_sqs
            except Exception as e:
                logging.debug(f"Could not check signal_quality_scores max date: {e}")

            if since is None:
                try:
                    with DatabaseContext('read') as wm_cur:
                        wm_cur.execute(
                            "SELECT MAX(date) FROM swing_trader_scores WHERE symbol = %s",
                            (symbol,),
                        )
                        wm_row = wm_cur.fetchone()
                    if wm_row and wm_row[0]:
                        since = wm_row[0] if isinstance(wm_row[0], date) else date.fromisoformat(str(wm_row[0]))
                except Exception as e:
                    logging.warning(f"Could not read swing_trader_scores watermark for {symbol}: {e}")

            if since is None:
                start = end - timedelta(days=30)
            else:
                # Use since - 1d overlap (standard across loaders) so that if
                # signal_quality_scores finishes after an earlier swing score run,
                # a re-run will recompute scores for the boundary date.
                since_date = since if isinstance(since, date) else date.fromisoformat(str(since).split('T')[0])
                start = since_date - timedelta(days=1)

            if start > end:
                return None

            # FIX #5: Pre-flight validation of all 4 source table dependencies
            validation_failures = self._validate_source_dependencies(symbol, end)
            if validation_failures:
                for failure_reason in validation_failures:
                    self._log_rejection_if_available(symbol, end, failure_reason)
                logging.debug(f"{symbol}: Swing score skipped due to source data: {validation_failures}")
                return None

            with DatabaseContext('read') as cur:
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
        except Exception as e:
            logging.debug(f"Swing score computation error for {symbol}: {e}")
            return None

    def _load_config_val(self, key: str, default):
        """Load a config value from AlgoConfig, with fallback to default."""
        try:
            from algo.algo_config import get_config
            val = get_config().get(key)
            return val if val is not None else default
        except Exception as e:
            logging.debug(f"_load_config_val({key}) failed: {e}")
            return default

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

            # Compute weighted score (0-100) matching SwingTraderScore weights:
            # setup=25, trend=20, momentum=20, volume=12, fundamentals=10, sector=8, multi_tf=5
            weighted_score = (
                (setup / 100.0) * 25 +
                (trend / 100.0) * 20 +
                (momentum / 100.0) * 20 +
                (volume / 100.0) * 12 +
                (fundamentals / 100.0) * 10 +
                (sector / 100.0) * 8 +
                (multi_tf / 100.0) * 5
            )

            grade = GradeClassifier.classify_swing_score(weighted_score)

            pass_gates = composite >= 75
            fail_reason = None if pass_gates else (
                'Low composite score' if composite < 45 else 'Below quality threshold'
            )

            return {
                'symbol': symbol,
                'date': score_date,
                'score': round(weighted_score, 2),
                'components': json.dumps({
                    'grade': grade,
                    'composite_sqs': round(composite, 1),
                    'pass_gates': pass_gates,
                    'fail_reason': fail_reason,
                    # Raw 0-100 scores — used by SwingCandidates.jsx component bars
                    'setup':       round(setup, 1),
                    'trend':       round(trend, 1),
                    'momentum':    round(momentum, 1),
                    'volume':      round(volume, 1),
                    'fundamentals': round(fundamentals, 1),
                    'sector':      round(sector, 1),
                    'multi_tf':    round(multi_tf, 1),
                    # Weighted pts breakdown — used by algo_filter_pipeline.py
                    'setup_quality':   {'pts': round((setup / 100.0) * 25, 1), 'max': 25},
                    'trend_quality':   {'pts': round((trend / 100.0) * 20, 1), 'max': 20},
                    'momentum_rs':     {'pts': round((momentum / 100.0) * 20, 1), 'max': 20},
                    'volume_quality':  {'pts': round((volume / 100.0) * 12, 1), 'max': 12},
                    'fundamentals_quality': {'pts': round((fundamentals / 100.0) * 10, 1), 'max': 10},
                    'sector_industry': {'pts': round((sector / 100.0) * 8, 1), 'max': 8},
                    'multi_timeframe': {'pts': round((multi_tf / 100.0) * 5, 1), 'max': 5},
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

    def _validate_source_dependencies(self, symbol: str, end_date: date) -> Optional[List[str]]:
        """Validate all 4 source tables have data for THIS SYMBOL on end_date.

        Per-symbol check only — no batch coverage check. Reason: batch coverage
        against all active symbols (10,000+) would always fail since source tables
        only contain data for qualifying symbols (~300-6000). The algo only needs
        a good candidate pool, not 100% of all active symbols.

        Returns: None if all sources OK, list of failure reasons if any source missing.
        """
        failures = []
        source_tables = [
            ("signal_quality_scores", "composite_sqs"),
            ("buy_sell_daily", "signal"),
            ("trend_template_data", "minervini_trend_score"),
            ("technical_data_daily", "rsi"),
        ]

        try:
            with DatabaseContext('read') as cur:
                for table_name, required_col in source_tables:
                    table_safe = assert_safe_table(table_name)
                    cur.execute(
                        psycopg2.sql.SQL("SELECT COUNT(*) FROM {} WHERE symbol = %s AND date = %s").format(
                            psycopg2.sql.Identifier(table_safe)
                        ),
                        (symbol, end_date)
                    )
                    if cur.fetchone()[0] == 0:
                        failures.append(f"{table_name}_missing")

        except Exception as e:
            logger.debug(f"Source validation failed for {symbol}: {e}")
            failures.append("validation_error")

        return failures if failures else None

    def _log_rejection_if_available(self, symbol: str, signal_date: date, reason: str):
        """FIX #9: Log signal rejection to signal_rejection_log for observability."""
        try:
            with DatabaseContext('write') as cur:
                cur.execute("""
                    INSERT INTO signal_rejection_log
                    (signal_source_table, rejection_reason, symbol, signal_date, rejected_at_tier, created_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                """, ("swing_trader_scores", reason, symbol, signal_date, "loader"))
        except Exception as e:
            logger.debug(f"Could not log rejection: {e}")

def main():
    import time
    from utils.database_context import DatabaseContext
    from datetime import datetime

    start_time = time.time()
    parser = argparse.ArgumentParser(description="Swing Trader Scores Loader")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols")
    parser.add_argument("--parallelism", type=int, default=get_default_parallelism("swing_trader_scores"), help="Concurrent workers")
    args = parser.parse_args()

    symbols = args.symbols.split(",") if args.symbols else get_active_symbols(timeout_secs=60)

    logger.info(f"Starting swing_trader_scores loader with {len(symbols)} symbols, parallelism={args.parallelism}")

    # NOTE: For large-scale production (5000+ symbols), consider using load_swing_trader_scores_vectorized.py
    # which is 3-5x faster by fetching all data in bulk queries and computing scores vectorized.
    # For intraday updates during market hours, use: python3 load_swing_trader_scores_vectorized.py --today (5-15 min)

    loader = SwingTraderScoresLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    fail_rate = stats.get("symbols_failed", 0) / max(len(symbols), 1)
    duration_seconds = time.time() - start_time

    # Log execution time for performance monitoring
    try:
        with DatabaseContext('write') as cur:
            cur.execute("""
                INSERT INTO data_loader_runs (
                    loader_name, table_name, run_date, status, records_loaded,
                    error_message, duration_seconds, started_at, completed_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, NOW(), NOW()
                )
                ON CONFLICT (loader_name, run_date) DO UPDATE SET
                    status = EXCLUDED.status,
                    records_loaded = EXCLUDED.records_loaded,
                    duration_seconds = EXCLUDED.duration_seconds,
                    completed_at = NOW()
            """, (
                'swing_trader_scores',
                'swing_trader_scores',
                datetime.now(timezone.utc).date(),
                'completed' if fail_rate <= 0.05 else 'failed',
                stats.get("symbols_processed", 0),
                str(stats.get("symbols_failed", 0)) if fail_rate > 0.05 else None,
                round(duration_seconds, 2)
            ))
    except Exception as e:
        logger.error(f"Failed to log execution time: {e}")

    if fail_rate > 0.05:
        logger.error(f"Too many failures: {stats['symbols_failed']}/{len(symbols)} ({fail_rate*100:.1f}%)")
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())

