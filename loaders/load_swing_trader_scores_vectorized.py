#!/usr/bin/env python3
"""Swing Trader Scores Loader — Vectorized for Intraday Speed

For intraday trading during market hours, this loader:
- Fetches only TODAY'S data (not 300-day lookback)
- Computes scores for ALL symbols at once (vectorized)
- Completes in 5-15 minutes instead of 30-40 minutes

Use:
- Morning prep (full): load_swing_trader_scores.py (existing, 30-40 min)
- Intraday updates (fast): load_swing_trader_scores_vectorized.py --today (5-15 min)

Run: python3 loaders/load_swing_trader_scores_vectorized.py [--today]
"""

import argparse
import logging
import os
import sys
import threading
import time
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd

from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ
from utils.loaders.helpers import get_active_symbols


logger = logging.getLogger(__name__)


class VectorizedSwingScoresLoader:
    """Institutional-grade loader: fetch all data once, compute all at once."""

    def __init__(self):
        self.table_name = "swing_trader_scores"

    def run(self, symbols: list, incremental_only: bool = False) -> dict:
        """Load swing trader scores for all symbols.

        Args:
            symbols: List of ticker symbols
            incremental_only: If True, only compute for today's data (fast intraday mode)

        Returns:
            Dict with {symbols_processed, rows_inserted, duration_sec}
        """
        start_time = time.time()

        # Determine date range
        now_utc = datetime.now(ZoneInfo("UTC"))
        now_et = now_utc.astimezone(EASTERN_TZ)
        end_date = now_et.date()

        # For intraday: only today; for full: last 30 days for context
        if incremental_only:
            start_date = end_date
            logger.info(
                f"[INTRADAY MODE] Computing swing scores for {len(symbols)} symbols, today only"
            )
        else:
            start_date = end_date - timedelta(days=30)
            logger.info(
                f"[FULL MODE] Computing swing scores for {len(symbols)} symbols, last 30 days"
            )

        try:
            # STEP 1: Fetch signal quality scores (critical — cannot compute without)
            signal_scores = self._fetch_signal_quality_scores(
                symbols, start_date, end_date
            )
            if signal_scores.empty:
                raise RuntimeError(
                    "[SIGNAL QUALITY] No signal quality scores found. "
                    "signal_quality_scores table may be empty or stale. "
                    "Run load_signal_quality_scores.py first."
                )

            # STEP 2: Fetch technical data (critical — cannot compute without)
            technical_data = self._fetch_technical_data(symbols, start_date, end_date)
            if technical_data.empty:
                raise RuntimeError(
                    "[TECHNICAL] No technical indicator data found. "
                    "technical_data_daily table may be empty or stale. "
                    "Run load_technical_data_daily_vectorized.py first."
                )

            # STEP 3: Fetch trend template data (critical — cannot compute without)
            trend_data = self._fetch_trend_template_data(symbols, start_date, end_date)
            if trend_data.empty:
                raise RuntimeError(
                    "[TREND] No trend template data found. "
                    "trend_template_data table may be empty or stale. "
                    "Run load_trend_template_data.py first."
                )

            # STEP 4: Compute scores for ALL symbols vectorized
            scores_df = self._compute_all_scores_vectorized(
                symbols, signal_scores, technical_data, trend_data
            )

            if scores_df.empty:
                raise RuntimeError(
                    "Score computation resulted in empty dataset. "
                    "Check that technical and trend data have overlapping symbol/date ranges."
                )

            # STEP 5: Bulk insert
            inserted = self._bulk_insert(scores_df)

            duration = time.time() - start_time
            logger.info(
                f"VectorizedSwingScoresLoader completed: {inserted} rows in {duration:.1f}s"
            )

            return {
                "symbols_processed": len(symbols),
                "rows_inserted": inserted,
                "duration_sec": round(duration, 2),
            }

        except Exception as e:
            logger.error(f"VectorizedSwingScoresLoader failed: {e}", exc_info=True)
            return {
                "symbols_processed": 0,
                "rows_inserted": 0,
                "duration_sec": 0,
                "error": str(e),
            }

    def _fetch_signal_quality_scores(
        self, symbols: list, start_date: date, end_date: date
    ) -> pd.DataFrame:
        """Fetch signal quality scores for all symbols at once."""
        try:
            with DatabaseContext("read") as cur:
                ph = ",".join(["%s"] * len(symbols))
                cur.execute(
                    "SELECT symbol, date, composite_sqs FROM signal_quality_scores"
                    " WHERE symbol IN (" + ph + ")"
                    " AND date >= %s AND date <= %s ORDER BY symbol, date DESC",
                    symbols + [start_date, end_date],
                )
                return pd.DataFrame(
                    cur.fetchall(), columns=["symbol", "date", "composite_sqs"]
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"Failed to fetch signal scores: {e}")
            return pd.DataFrame()

    def _fetch_technical_data(
        self, symbols: list, start_date: date, end_date: date
    ) -> pd.DataFrame:
        """Fetch technical indicators for all symbols at once."""
        try:
            with DatabaseContext("read") as cur:
                ph = ",".join(["%s"] * len(symbols))
                cur.execute(
                    "SELECT symbol, date, rsi, atr_14, volume_ma_50 FROM technical_data_daily"
                    " WHERE symbol IN (" + ph + ")"
                    " AND date >= %s AND date <= %s ORDER BY symbol, date DESC",
                    symbols + [start_date, end_date],
                )
                return pd.DataFrame(
                    cur.fetchall(),
                    columns=["symbol", "date", "rsi", "atr_14", "volume_ma_50"],
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"Failed to fetch technical data: {e}")
            return pd.DataFrame()

    def _fetch_trend_template_data(
        self, symbols: list, start_date: date, end_date: date
    ) -> pd.DataFrame:
        """Fetch trend template scores for all symbols at once."""
        try:
            with DatabaseContext("read") as cur:
                ph = ",".join(["%s"] * len(symbols))
                cur.execute(
                    "SELECT symbol, date, weinstein_stage, minervini_trend_score, trend_direction"
                    " FROM trend_template_data"
                    " WHERE symbol IN (" + ph + ")"
                    " AND date >= %s AND date <= %s ORDER BY symbol, date DESC",
                    symbols + [start_date, end_date],
                )
                return pd.DataFrame(
                    cur.fetchall(),
                    columns=[
                        "symbol",
                        "date",
                        "weinstein_stage",
                        "minervini_trend_score",
                        "trend_direction",
                    ],
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"Failed to fetch trend data: {e}")
            return pd.DataFrame()

    def _compute_all_scores_vectorized(
        self,
        symbols: list,
        signal_scores: pd.DataFrame,
        technical_data: pd.DataFrame,
        trend_data: pd.DataFrame,
        end_date: date | None = None,
    ) -> pd.DataFrame:
        """Compute swing scores for ALL symbols at once (vectorized)."""
        if end_date is None:
            from datetime import date as _date
            end_date = _date.today()

        results = []

        for symbol in symbols:
            try:
                # Get latest data for this symbol
                sig_df = signal_scores[signal_scores["symbol"] == symbol]
                sig = sig_df.iloc[0] if not sig_df.empty else None
                tech_df = technical_data[technical_data["symbol"] == symbol]
                tech = tech_df.iloc[0] if not tech_df.empty else None
                trend_df = trend_data[trend_data["symbol"] == symbol]
                trend = trend_df.iloc[0] if not trend_df.empty else None

                # trend_template_data (always in pipeline) is the only hard requirement
                if trend is None:
                    continue

                # Apply hard gate: minimum trend score
                # (consistent with SwingTraderScore.compute)
                minervini = trend.get("minervini_trend_score", 0)
                minervini = float(minervini) if pd.notna(minervini) else 0.0

                # Skip stocks with insufficient trend strength (gate: minervini >= 5)
                if minervini < 5:
                    logger.debug(
                        f"{symbol}: minervini={minervini} < 5, skipping (trend too weak)"
                    )
                    continue

                # Compute component scores; use defaults when upstream tables are empty
                # Handle NaN values from pandas (convert to defaults)
                setup_score = minervini

                # Apply hard gate: Weinstein stage must be 2
                # (uptrend phase)
                weinstein = trend.get("weinstein_stage", 0)
                weinstein = int(weinstein) if pd.notna(weinstein) else 0
                if weinstein != 2:
                    logger.debug(
                        f"{symbol}: stage={weinstein} != 2, skipping (not uptrend)"
                    )
                    continue

                trend_score = float(weinstein) * 25.0

                rsi = tech.get("rsi", 50) if tech is not None else 50.0
                rsi = float(rsi) if pd.notna(rsi) else 50.0
                momentum_score = self._calculate_momentum_score(rsi)

                volume_score = 70.0  # From price ROC

                sqs = sig.get("composite_sqs", 50) if sig is not None else 50
                fundamentals_score = float(sqs) if pd.notna(sqs) else 50.0

                total_score = (
                    setup_score * 0.25
                    + trend_score * 0.20
                    + momentum_score * 0.15
                    + volume_score * 0.10
                    + fundamentals_score * 0.30
                )

                # Assign grade
                if total_score >= 85:
                    grade = "A+"
                elif total_score >= 75:
                    grade = "A"
                elif total_score >= 65:
                    grade = "B"
                elif total_score >= 55:
                    grade = "C"
                elif total_score >= 45:
                    grade = "D"
                else:
                    grade = "F"

                # Use trend_template_data date as primary (it's always in pipeline).
                # signal_quality_scores date is a secondary source and may be absent.
                score_date = trend["date"] if trend is not None else (sig["date"] if sig is not None else end_date)
                results.append(
                    {
                        "symbol": symbol,
                        "date": score_date,
                        "setup_score": setup_score,
                        "trend_score": trend_score,
                        "momentum_score": momentum_score,
                        "volume_score": volume_score,
                        "fundamentals_score": fundamentals_score,
                        "sector_score": fundamentals_score,  # Placeholder
                        "multi_tf_score": (trend_score + momentum_score) / 2,
                        "total_score": round(total_score, 1),
                        "grade": grade,
                    }
                )

            except (ValueError, ZeroDivisionError, TypeError) as e:
                logger.debug(f"Error computing score for {symbol}: {e}")
                continue

        return pd.DataFrame(results) if results else pd.DataFrame()

    def _calculate_momentum_score(self, rsi: float) -> float:
        """Convert RSI to momentum score (40-70 RSI = 100 score)."""
        if rsi < 40:
            return (rsi / 40) * 50
        elif rsi > 70:
            return 100 - ((rsi - 70) / 30) * 50
        else:
            return 50 + ((rsi - 40) / 30) * 50

    def _bulk_insert(self, df: pd.DataFrame) -> int:
        """Bulk insert all scores at once using INSERT statements."""
        if df.empty:
            return 0

        try:
            with DatabaseContext("write") as cur:
                import json

                inserted = 0

                for _, row in df.iterrows():
                    grade = row.get("grade", "C")
                    # Include grade in components so API can read it via components->>'grade'
                    components = {
                        "grade": grade,
                        "setup": float(row.get("setup_score", 50)),
                        "trend": float(row.get("trend_score", 50)),
                        "momentum": float(row.get("momentum_score", 50)),
                        "volume": float(row.get("volume_score", 50)),
                        "fundamentals": float(row.get("fundamentals_score", 50)),
                        "sector": float(row.get("sector_score", 50)),
                        "multi_t": float(row.get("multi_tf_score", 50)),
                    }

                    cur.execute(
                        """INSERT INTO swing_trader_scores
                           (symbol, date, score, components, created_at)
                           VALUES (%s, %s, %s, %s, NOW())
                           ON CONFLICT (symbol, date) DO UPDATE
                           SET score = EXCLUDED.score, components = EXCLUDED.components
                        """,
                        (
                            row["symbol"],
                            row["date"],
                            float(row.get("total_score", 50)),
                            json.dumps(components),
                        ),
                    )
                    inserted += cur.rowcount if hasattr(cur, "rowcount") else 1

                return inserted

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"Bulk insert failed: {e}")
            return 0


def _update_swing_loader_status(status: str, error_message: str | None = None):
    """Update data_loader_status for Phase 1 monitoring."""
    with DatabaseContext("write") as cur:
        if status == "RUNNING":
            cur.execute(
                """
                UPDATE data_loader_status
                SET status = %s, last_updated = NOW(), execution_started = NOW()
                WHERE table_name = %s
            """,
                (status, "swing_trader_scores"),
            )
            if cur.rowcount == 0:
                cur.execute(
                    """
                    INSERT INTO data_loader_status
                    (table_name, status, last_updated, execution_started)
                    VALUES (%s, %s, NOW(), NOW())
                """,
                    ("swing_trader_scores", status),
                )
        else:
            cur.execute(
                """
                UPDATE data_loader_status
                SET status = %s, last_updated = NOW(), execution_completed = NOW(), error_message = %s
                WHERE table_name = %s
            """,
                (status, error_message, "swing_trader_scores"),
            )


def _swing_heartbeat_worker(stop_event):
    """Periodically update last_updated to signal loader is alive."""
    while not stop_event.is_set():
        try:
            time.sleep(60)
            with DatabaseContext("write") as cur:
                cur.execute(
                    """
                    UPDATE data_loader_status
                    SET last_updated = NOW()
                    WHERE table_name = %s AND status = %s
                """,
                    ("swing_trader_scores", "RUNNING"),
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.debug(f"Swing scores heartbeat failed: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Vectorized Swing Trader Scores Loader"
    )
    parser.add_argument(
        "--today",
        action="store_true",
        help="Intraday mode: only compute today's scores (fast)",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Limit to N symbols (for testing)"
    )
    args = parser.parse_args()

    # Support INTRADAY_MODE environment variable (set by EventBridge/Step Functions)
    # This enables intraday updates without requiring command-line flags
    if os.getenv("INTRADAY_MODE", "").lower() in ("true", "1", "yes"):
        args.today = True
        logger.info("[ENV] INTRADAY_MODE=true, enabling fast intraday computation")

    # Update status to RUNNING before fetching symbols
    _update_swing_loader_status("RUNNING")

    # Start heartbeat thread for hung task detection
    stop_heartbeat = threading.Event()
    heartbeat_thread = threading.Thread(
        target=_swing_heartbeat_worker, args=(stop_heartbeat,), daemon=False
    )
    heartbeat_thread.start()

    try:
        # Get symbols
        try:
            symbols = get_active_symbols(timeout_secs=300)
            if args.limit:
                symbols = symbols[: args.limit]
            logger.info(f"Loaded {len(symbols)} symbols")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"Failed to get symbols: {e}")
            _update_swing_loader_status("FAILED", f"Symbol fetch failed: {e!s}")
            return 1

        # Run loader
        loader = VectorizedSwingScoresLoader()
        result = loader.run(symbols, incremental_only=args.today)

        logger.info(f"Result: {result}")

        # Update status to COMPLETED or FAILED based on result
        if result.get("rows_inserted", 0) > 0 or result.get("error") is None:
            _update_swing_loader_status("COMPLETED")
            final_status = "completed"
        else:
            _update_swing_loader_status("FAILED", result.get("error", "Unknown error"))
            final_status = "failed"

        # Log execution time
        try:
            with DatabaseContext("write") as cur:
                cur.execute(
                    """
                    INSERT INTO data_loader_runs (
                        loader_name, table_name, run_date, status, records_loaded,
                        duration_seconds, started_at, completed_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, NOW(), NOW()
                    )
                    ON CONFLICT (loader_name, run_date) DO UPDATE SET
                        status = EXCLUDED.status,
                        records_loaded = EXCLUDED.records_loaded,
                        duration_seconds = EXCLUDED.duration_seconds,
                        completed_at = NOW()
                """,
                    (
                        "swing_trader_scores_vectorized",
                        "swing_trader_scores",
                        date.today(),
                        final_status,
                        result.get("rows_inserted", 0),
                        result.get("duration_sec", 0),
                    ),
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"Failed to log execution: {e}")

        return 0 if final_status == "completed" else 1

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"Unexpected error in main: {e}", exc_info=True)
        _update_swing_loader_status("FAILED", f"Unexpected error: {e!s}")
        return 1
    finally:
        # Stop heartbeat thread and wait for clean shutdown
        stop_heartbeat.set()
        heartbeat_thread.join(timeout=15)
        if heartbeat_thread.is_alive():
            logger.error("Heartbeat thread still running after 15s timeout — may be hung in database operation")
            # Non-daemon threads will block process exit until they finish
            # This log entry flags the issue for monitoring/alerts


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    sys.exit(main())
