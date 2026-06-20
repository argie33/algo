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

from loaders.loader_helper import setup_imports
from utils.safe_data_conversion import safe_float


setup_imports()

import json
import logging
from datetime import date, timedelta, timezone
from typing import Dict, List, Optional

import psycopg2.sql

from utils.db.context import DatabaseContext
from utils.db.sql_safety import assert_safe_table


logger = logging.getLogger(__name__)
from loaders.runner import run_loader
from utils.infrastructure.timezone import EASTERN_TZ
from utils.optimal_loader import OptimalLoader
from utils.signals.grade_classifier import GradeClassifier


class SwingTraderScoresLoader(OptimalLoader):
    table_name = "swing_trader_scores"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def _prepare_batch_context(self) -> None:
        """Load shared data once to avoid N+1 queries (ROOT CAUSE #4 FIX).

        Caches end_date and signal_quality_scores max date to avoid per-symbol computation.
        """
        from datetime import datetime

        from algo.infrastructure import MarketCalendar

        self._batch_context = {}

        try:
            now_utc = datetime.now(timezone.utc)
            now_et = now_utc.astimezone(EASTERN_TZ)
            end = now_et.date()

            while end > date(2020, 1, 1) and not MarketCalendar.is_trading_day(end):
                end = end - timedelta(days=1)

            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT MAX(date) FROM signal_quality_scores WHERE date <= %s",
                    (end,),
                )
                fb_row = cur.fetchone()
                last_sqs_date = fb_row[0] if fb_row and fb_row[0] else None
                if last_sqs_date:
                    last_sqs = (
                        last_sqs_date
                        if isinstance(last_sqs_date, date)
                        else date.fromisoformat(str(last_sqs_date))
                    )
                    if last_sqs < end:
                        end = last_sqs

            self._batch_context = {
                "end_date": end,
            }
            logger.debug(f"Batch context: end={end}")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"[BATCH_CONTEXT] Failed to prepare batch context for swing_trader_scores: {e}. "
                "Cannot proceed without end_date and data coverage verification."
            )

    def fetch_incremental(self, symbol: str, since: date | None):
        """Compute swing trader scores with 7-component breakdown.

        Validates all 3 source tables before computing scores.
        """
        from datetime import datetime

        from algo.infrastructure import MarketCalendar

        try:
            # ROOT CAUSE #4 FIX: Use cached end_date from batch context (computed once for all symbols)
            # instead of recomputing trading day verification for each symbol.
            if self._batch_context and "end_date" in self._batch_context:
                end = self._batch_context["end_date"]
            else:
                # Fallback if batch context unavailable
                now_utc = datetime.now(timezone.utc)
                now_et = now_utc.astimezone(EASTERN_TZ)
                end = now_et.date()

                while end > date(2020, 1, 1) and not MarketCalendar.is_trading_day(end):
                    end = end - timedelta(days=1)

                # Fallback: check signal_quality_scores max date if batch context failed
                try:
                    with DatabaseContext("read") as fbc:
                        fbc.execute(
                            "SELECT MAX(date) FROM signal_quality_scores WHERE date <= %s",
                            (end,),
                        )
                        fb_row = fbc.fetchone()
                        last_sqs_date = fb_row[0] if fb_row and fb_row[0] else None
                        if last_sqs_date:
                            last_sqs = (
                                last_sqs_date
                                if isinstance(last_sqs_date, date)
                                else date.fromisoformat(str(last_sqs_date))
                            )
                            if last_sqs < end:
                                end = last_sqs
                except psycopg2.Error as e:
                    raise RuntimeError(
                        f"[SWING_SCORES] Database error checking signal_quality_scores max date: {e}. "
                        "Cannot determine end date for score computation."
                    ) from e
                except (ValueError, TypeError) as e:
                    raise RuntimeError(
                        f"[SWING_SCORES] Data format error reading max date: {e}. "
                        "signal_quality_scores data may be corrupted."
                    ) from e

            if since is None:
                try:
                    with DatabaseContext("read") as wm_cur:
                        wm_cur.execute(
                            "SELECT MAX(date) FROM swing_trader_scores WHERE symbol = %s",
                            (symbol,),
                        )
                        wm_row = wm_cur.fetchone()
                    if wm_row and wm_row[0]:
                        since = (
                            wm_row[0]
                            if isinstance(wm_row[0], date)
                            else date.fromisoformat(str(wm_row[0]))
                        )
                except psycopg2.Error as e:
                    raise RuntimeError(
                        f"[WATERMARK] Database error reading swing_trader_scores watermark for {symbol}: {e}. "
                        "Cannot determine incremental load point."
                    ) from e
                except (ValueError, TypeError) as e:
                    raise RuntimeError(
                        f"[WATERMARK] Data format error reading watermark for {symbol}: {e}. "
                        "Watermark data may be corrupted."
                    ) from e

            if since is None:
                start = end - timedelta(days=30)
            else:
                # Use since - 1d overlap (standard across loaders) so that if
                # signal_quality_scores finishes after an earlier swing score run,
                # a re-run will recompute scores for the boundary date.
                since_date = (
                    since
                    if isinstance(since, date)
                    else date.fromisoformat(str(since).split("T")[0])
                )
                start = since_date - timedelta(days=1)

            if start > end:
                return None

            # FIX #5: Pre-flight validation of all 4 source table dependencies
            validation_failures = self._validate_source_dependencies(symbol, end)
            if validation_failures:
                for failure_reason in validation_failures:
                    self._log_rejection_if_available(symbol, end, failure_reason)
                logger.debug(
                    f"{symbol}: Swing score skipped due to source data: {validation_failures}"
                )
                return None

            with DatabaseContext("read") as cur:
                # Join signal_quality_scores with trend + technical data for component breakdown
                cur.execute(
                    """
                    SELECT
                        sqs.symbol,
                        sqs.date,
                        sqs.composite_sqs,
                        td.minervini_trend_score,
                        td.weinstein_stage,
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
                """,
                    (symbol, start, end),
                )
                rows = cur.fetchall()

                if not rows:
                    return None

                all_scores = []
                for row in rows:
                    score_row = self._compute_swing_score(row)
                    if score_row:
                        all_scores.append(score_row)

                return all_scores if all_scores else None
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"[SWING_SCORES] Failed to compute swing trader scores for {symbol}: {e}. "
                "Swing trading signal generation requires complete score computation."
            )

    def _load_config_val(self, key: str, default):
        """Load a config value from AlgoConfig, with fallback to default."""
        try:
            from algo.infrastructure import get_config

            val = get_config().get(key)
            return val if val is not None else default
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"[CONFIG] Failed to load config value '{key}': {e}. "
                "Swing scoring requires authoritative config parameters."
            )

    def _compute_swing_score(self, row) -> dict | None:
        """Compute swing trader score with 7-component breakdown.

        Input columns: symbol, date, composite_sqs, minervini_score, weinstein_stage,
                       rsi, roc_20d, mansfield_rs
        """
        if not row:
            return None

        try:
            (
                symbol,
                score_date,
                composite_sqs,
                minervini_score,
                weinstein_stage,
                rsi,
                roc_20d,
                mansfield_rs,
            ) = row

            composite = float(composite_sqs) if composite_sqs is not None else None

            # --- 7 component scores (0-100 each) ---

            # Setup: Minervini 8-point template completion (0-100)
            setup = (
                min(100.0, float(minervini_score) / 8.0 * 100.0)
                if minervini_score is not None
                else None
            )

            # Trend: Weinstein stage quality
            stage = int(weinstein_stage) if weinstein_stage is not None else None
            if stage == 2:
                trend = 100.0
            elif stage == 1:
                trend = 50.0
            elif stage == 3:
                trend = 25.0
            elif stage is not None:
                trend = 0.0
            else:
                trend = None

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
            fundamentals: float | None = composite

            # Sector: Mansfield RS if available (positive RS = sector leadership)
            sector: float | None = None
            if mansfield_rs is not None:
                rs = float(mansfield_rs)
                # Mansfield RS: 0 = at par, positive = outperforming, negative = underperforming
                sector = max(0.0, min(100.0, 50.0 + rs * 5.0))
            else:
                # Fallback to composite if available
                sector = composite

            # Multi-timeframe: blend of trend + momentum (confirming at multiple scales)
            trend_val = trend if trend is not None else 0.0
            momentum_val = momentum if momentum is not None else 0.0
            multi_tf_val = trend_val * 0.6 + momentum_val * 0.4
            # Only report multi_tf if at least one component is available
            multi_tf = multi_tf_val if (trend is not None or momentum is not None) else None

            # Compute weighted score with normalized weights for missing components.
            # Base weights: setup=25, trend=20, momentum=20, volume=12, fundamentals=10, sector=8, multi_tf=5
            base_weights = {
                "setup": 25,
                "trend": 20,
                "momentum": 20,
                "volume": 12,
                "fundamentals": 10,
                "sector": 8,
                "multi_tf": 5,
            }

            # Track which components are available (not None)
            available = {
                "setup": setup is not None,
                "trend": trend is not None,
                "momentum": momentum is not None,
                "volume": True,  # volume always computed (defaults to 50 if roc is None)
                "fundamentals": fundamentals is not None,
                "sector": sector is not None,
                "multi_tf": multi_tf is not None,
            }

            # Normalize weights: redistribute missing component weights to available components
            available_weight_sum = sum(w for k, w in base_weights.items() if available[k])
            normalized_weights = {}
            for key, weight in base_weights.items():
                if available[key] and available_weight_sum > 0:
                    normalized_weights[key] = weight / available_weight_sum * 100
                else:
                    normalized_weights[key] = 0

            # Compute weighted score using only non-None components
            weighted_score = (
                ((setup or 0) / 100.0) * normalized_weights["setup"]
                + ((trend or 0) / 100.0) * normalized_weights["trend"]
                + ((momentum or 0) / 100.0) * normalized_weights["momentum"]
                + ((volume or 0) / 100.0) * normalized_weights["volume"]
                + ((fundamentals or 0) / 100.0) * normalized_weights["fundamentals"]
                + ((sector or 0) / 100.0) * normalized_weights["sector"]
                + ((multi_tf or 0) / 100.0) * normalized_weights["multi_tf"]
            )

            grade = GradeClassifier.classify_swing_score(weighted_score)

            pass_gates = composite is not None and composite >= 75
            fail_reason = (
                None
                if pass_gates
                else (
                    "Low composite score"
                    if composite is None or composite < 45
                    else "Below quality threshold"
                )
            )

            return {
                "symbol": symbol,
                "date": score_date,
                "score": round(weighted_score, 2),
                "components": json.dumps(
                    {
                        "grade": grade,
                        "composite_sqs": round(composite, 1) if composite is not None else None,
                        "pass_gates": pass_gates,
                        "fail_reason": fail_reason,
                        # Raw 0-100 scores — used by SwingCandidates.jsx component bars
                        "setup": round(setup, 1) if setup is not None else None,
                        "trend": round(trend, 1) if trend is not None else None,
                        "momentum": round(momentum, 1) if momentum is not None else None,
                        "volume": round(volume, 1),
                        "fundamentals": round(fundamentals, 1) if fundamentals is not None else None,
                        "sector": round(sector, 1) if sector is not None else None,
                        "multi_tf": round(multi_tf, 1) if multi_tf is not None else None,
                        # Weighted pts breakdown — used by algo_filter_pipeline.py
                        "setup_quality": {
                            "pts": round((setup or 0) / 100.0 * 25, 1),
                            "max": 25,
                        },
                        "trend_quality": {
                            "pts": round((trend or 0) / 100.0 * 20, 1),
                            "max": 20,
                        },
                        "momentum_rs": {
                            "pts": round((momentum or 0) / 100.0 * 20, 1),
                            "max": 20,
                        },
                        "volume_quality": {
                            "pts": round((volume or 0) / 100.0 * 12, 1),
                            "max": 12,
                        },
                        "fundamentals_quality": {
                            "pts": round((fundamentals or 0) / 100.0 * 10, 1),
                            "max": 10,
                        },
                        "sector_industry": {
                            "pts": round((sector or 0) / 100.0 * 8, 1),
                            "max": 8,
                        },
                        "multi_timeframe": {
                            "pts": round((multi_tf or 0) / 100.0 * 5, 1),
                            "max": 5,
                        },
                    }
                ),
            }
        except Exception as e:
            raise RuntimeError(
                f"[SWING_SCORE] Failed to compute swing score for {symbol}: {e}. "
                "Score computation is authoritative for swing trading signals."
            )

    def transform(self, rows):
        """Rows are clean."""
        return rows

    def _validate_row(self, row: dict) -> bool:
        """Validate swing score row."""
        if not super()._validate_row(row):
            return False
        return (
            row.get("symbol") is not None
            and row.get("date") is not None
            and row.get("score") is not None
            and 0 <= float(row.get("score", 0)) <= 100
        )

    def _validate_source_dependencies(
        self, symbol: str, end_date: date
    ) -> list[str] | None:
        """Validate all 3 source tables have data for THIS SYMBOL on end_date.

        Per-symbol check only — no batch coverage check. Reason: batch coverage
        against all active symbols (10,000+) would always fail since source tables
        only contain data for qualifying symbols (~300-6000). The algo only needs
        a good candidate pool, not 100% of all active symbols.

        Returns: None if all sources OK, list of failure reasons if any source missing.
        """
        failures = []
        source_tables = [
            ("signal_quality_scores", "composite_sqs"),
            ("trend_template_data", "minervini_trend_score"),
            ("technical_data_daily", "rsi"),
        ]

        try:
            with DatabaseContext("read") as cur:
                for table_name, required_col in source_tables:
                    table_safe = assert_safe_table(table_name)
                    cur.execute(
                        psycopg2.sql.SQL(
                            "SELECT COUNT(*) FROM {} WHERE symbol = %s AND date = %s"
                        ).format(psycopg2.sql.Identifier(table_safe)),
                        (symbol, end_date),
                    )
                    row = cur.fetchone()
                    if row is None or row[0] is None:
                        raise RuntimeError(f"Count query failed for {table_name} {symbol}")
                    if row[0] == 0:
                        failures.append(f"{table_name}_missing")

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.debug(f"Source validation failed for {symbol}: {e}")
            failures.append("validation_error")

        return failures if failures else None

    def _log_rejection_if_available(self, symbol: str, signal_date: date, reason: str):
        """Log signal rejection to signal_rejection_log for observability (non-fatal)."""
        try:
            with DatabaseContext("write") as cur:
                cur.execute(
                    """
                    INSERT INTO signal_rejection_log
                    (signal_source_table, rejection_reason, symbol, signal_date, rejected_at_tier, created_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                """,
                    ("swing_trader_scores", reason, symbol, signal_date, "loader"),
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.debug(
                f"[SIGNAL_REJECTION_LOG] Could not log rejection for {symbol}: {e}"
            )



if __name__ == "__main__":
    sys.exit(run_loader(SwingTraderScoresLoader))
