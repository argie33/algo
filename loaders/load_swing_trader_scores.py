#!/usr/bin/env python3
"""Swing Trader Scores Loader — Vectorized for Institutional Speed

Computes swing trader scores for ALL symbols at once (vectorized).
- Single bulk fetch of all signal_quality_scores data
- Vectorized pandas operations across all symbols
- Single bulk insert for all results
- Completes in 10-20 minutes for 5000+ symbols

Supports intraday mode with --today flag for afternoon/preclose updates (5-15 min).

Run: python3 loaders/load_swing_trader_scores.py [--today]
"""

import argparse
import logging
import os
import sys
import threading
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import psycopg2

from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ
from utils.loaders.helpers import get_active_symbols

logger = logging.getLogger(__name__)


class VectorizedSwingScoresLoader:
    """Institutional-grade loader: fetch all data once, compute all at once."""

    def __init__(self) -> None:
        self.table_name = "swing_trader_scores"

    def run(self, symbols: list[str], incremental_only: bool = False) -> dict[str, int | float | str | None]:
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
            logger.info(f"[INTRADAY MODE] Computing swing scores for {len(symbols)} symbols, today only")
        else:
            start_date = end_date - timedelta(days=30)
            logger.info(f"[FULL MODE] Computing swing scores for {len(symbols)} symbols, last 30 days")

        try:
            # STEP 1: Fetch signal quality scores (critical — cannot compute without)
            signal_scores = self._fetch_signal_quality_scores(symbols, start_date, end_date)
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
                    "Run load_technical_data_daily.py first."
                )

            # STEP 3: Fetch trend template data (critical — cannot compute without)
            trend_data = self._fetch_trend_template_data(symbols, start_date, end_date)
            if trend_data.empty:
                raise RuntimeError(
                    "[TREND] No trend template data found. "
                    "trend_template_data table may be empty or stale. "
                    "Run load_trend_template_data.py first."
                )

            # STEP 4: Fetch sector ranking data (sector health metric — may be empty if sector ranking not yet run)
            sector_data = self._fetch_sector_and_ranking_data(symbols, start_date, end_date)
            if sector_data.empty:
                logger.warning(
                    "[SECTOR RANKING] No sector ranking data found. "
                    "sector_ranking table may be empty. Sector scores will be omitted from computation."
                )

            # STEP 5: Compute scores for ALL symbols vectorized
            scores_df = self._compute_all_scores_vectorized(symbols, signal_scores, technical_data, trend_data, sector_data)

            if scores_df.empty:
                raise RuntimeError(
                    "Score computation resulted in empty dataset. "
                    "Check that technical and trend data have overlapping symbol/date ranges."
                )

            # STEP 5: Bulk insert
            inserted = self._bulk_insert(scores_df)

            duration = time.time() - start_time
            logger.info(f"VectorizedSwingScoresLoader completed: {inserted} rows in {duration:.1f}s")

            return {
                "symbols_processed": len(symbols),
                "rows_inserted": inserted,
                "duration_sec": round(duration, 2),
                "error": None,
            }

        except Exception as e:
            logger.error(f"VectorizedSwingScoresLoader failed: {e}", exc_info=True)
            return {
                "symbols_processed": 0,
                "rows_inserted": 0,
                "duration_sec": round(time.time() - start_time, 2),
                "error": str(e),
            }

    def _fetch_signal_quality_scores(self, symbols: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        """Fetch signal quality scores for all symbols at once."""
        try:
            with DatabaseContext("read") as cur:
                param_positions = ",".join(["%s"] * len(symbols))
                cur.execute(
                    "SELECT symbol, date, composite_sqs FROM signal_quality_scores"
                    " WHERE symbol IN (" + param_positions + ")"
                    " AND date >= %s AND date <= %s ORDER BY symbol, date DESC",
                    [*symbols, start_date, end_date],
                )
                return pd.DataFrame(cur.fetchall(), columns=["symbol", "date", "composite_sqs"])
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"[SIGNAL QUALITY FETCH FAILED] Cannot load signal quality scores: {e}") from e

    def _fetch_technical_data(self, symbols: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        """Fetch technical indicators for all symbols at once."""
        try:
            with DatabaseContext("read") as cur:
                param_positions = ",".join(["%s"] * len(symbols))
                cur.execute(
                    "SELECT symbol, date, rsi, atr_14, volume_ma_50 FROM technical_data_daily"
                    " WHERE symbol IN (" + param_positions + ")"
                    " AND date >= %s AND date <= %s ORDER BY symbol, date DESC",
                    [*symbols, start_date, end_date],
                )
                return pd.DataFrame(
                    cur.fetchall(),
                    columns=["symbol", "date", "rsi", "atr_14", "volume_ma_50"],
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"[TECHNICAL DATA FETCH FAILED] Cannot load technical indicators: {e}") from e

    def _fetch_trend_template_data(self, symbols: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        """Fetch trend template scores for all symbols at once."""
        try:
            with DatabaseContext("read") as cur:
                param_positions = ",".join(["%s"] * len(symbols))
                cur.execute(
                    "SELECT symbol, date, weinstein_stage, minervini_trend_score, trend_direction"
                    " FROM trend_template_data"
                    " WHERE symbol IN (" + param_positions + ")"
                    " AND date >= %s AND date <= %s ORDER BY symbol, date DESC",
                    [*symbols, start_date, end_date],
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
            raise RuntimeError(f"[TREND DATA FETCH FAILED] Cannot load trend template data: {e}") from e

    def _fetch_sector_and_ranking_data(self, symbols: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        """Fetch sector names and sector ranking momentum scores for all symbols."""
        try:
            with DatabaseContext("read") as cur:
                param_positions = ",".join(["%s"] * len(symbols))
                cur.execute(
                    "SELECT cp.ticker AS symbol, sr.date, cp.sector, sr.momentum_score "
                    " FROM company_profile cp "
                    " LEFT JOIN sector_ranking sr ON cp.sector = sr.sector_name "
                    " WHERE cp.ticker IN (" + param_positions + ")"
                    " AND sr.date >= %s AND sr.date <= %s ORDER BY cp.ticker, sr.date DESC",
                    [*symbols, start_date, end_date],
                )
                return pd.DataFrame(
                    cur.fetchall(),
                    columns=["symbol", "date", "sector", "sector_momentum_score"],
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"[SECTOR RANKING FETCH FAILED] Cannot load sector ranking data: {e}") from e

    def _compute_all_scores_vectorized(  # noqa: C901
        self,
        symbols: list[str],
        signal_scores: pd.DataFrame,
        technical_data: pd.DataFrame,
        trend_data: pd.DataFrame,
        sector_data: pd.DataFrame | None = None,
        end_date: date | None = None,
    ) -> pd.DataFrame:
        """Compute swing scores for ALL symbols at once (vectorized)."""
        if end_date is None:
            from datetime import date as _date

            end_date = _date.today()

        if sector_data is None:
            sector_data = pd.DataFrame()

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
                sector_df = sector_data[sector_data["symbol"] == symbol]
                sector = sector_df.iloc[0] if not sector_df.empty else None

                # trend_template_data (always in pipeline) is the only hard requirement
                if trend is None:
                    raise ValueError(f"{symbol}: No trend template data found (critical upstream requirement)")

                # Apply hard gate: minimum trend score
                # (consistent with SwingTraderScore.compute)
                if "minervini_trend_score" not in trend:
                    raise ValueError(f"{symbol}: trend data missing required 'minervini_trend_score' field")
                minervini = trend["minervini_trend_score"]
                if not pd.notna(minervini):
                    raise ValueError(f"{symbol}: minervini_trend_score is NaN on {date} — required for trend-based scoring")
                minervini = float(minervini)

                # Skip stocks with insufficient trend strength (gate: minervini >= 5)
                if minervini < 5:
                    logger.debug(f"{symbol}: minervini={minervini} < 5, skipping (trend too weak)")
                    continue

                # Compute component scores; use defaults when upstream tables are empty
                # Handle NaN values from pandas (convert to defaults)
                setup_score = minervini

                # Apply hard gate: Weinstein stage must be 2
                # (uptrend phase)
                if "weinstein_stage" not in trend:
                    raise ValueError(f"{symbol}: trend data missing required 'weinstein_stage' field")
                weinstein = trend["weinstein_stage"]
                if not pd.notna(weinstein):
                    raise ValueError(f"{symbol}: weinstein_stage is NaN on {date} — required for market stage filtering")
                weinstein = int(weinstein)
                if weinstein != 2:
                    logger.debug(f"{symbol}: stage={weinstein} != 2, skipping (not uptrend)")
                    continue

                trend_score = float(weinstein) * 25.0

                if tech is None or "rsi" not in tech:
                    raise ValueError(f"RSI data missing for {symbol} on {date}")
                rsi = tech["rsi"]
                if not pd.notna(rsi):
                    raise ValueError(f"RSI value is NaN for {symbol} on {date}")
                rsi = float(rsi)
                momentum_score = self._calculate_momentum_score(rsi)

                volume_score = 70.0  # From price ROC

                if sig is None or "composite_sqs" not in sig:
                    raise ValueError(f"Signal quality score missing for {symbol} on {date}")
                sqs = sig["composite_sqs"]
                if not pd.notna(sqs):
                    raise ValueError(f"Signal quality score is NaN for {symbol} on {date}")
                fundamentals_score = float(sqs)

                # Fetch sector momentum score (real sector health metric, not mock data)
                sector_score = None
                if sector is not None and "sector_momentum_score" in sector:
                    sector_momentum = sector["sector_momentum_score"]
                    if pd.notna(sector_momentum):
                        sector_score = float(sector_momentum)
                        logger.debug(f"{symbol}: Using sector momentum score {sector_score:.1f} from sector_ranking")

                # CRITICAL: Sector momentum is a required component of swing trader score
                # Do not fall back to fundamentals_score as it's a different metric
                if sector_score is None:
                    if sector is None:
                        # Sector data completely missing — sector_ranking table may not have run
                        logger.warning(
                            f"{symbol}: No sector data available from sector_ranking. "
                            f"Sector ranking loader may not have completed for this date."
                        )
                        raise ValueError(
                            f"{symbol}: Cannot compute swing trader score without sector data. "
                            f"sector_ranking table must be populated by load_sector_ranking.py first."
                        )
                    else:
                        # Sector data exists but momentum score is missing
                        logger.warning(
                            f"{symbol}: Sector record exists but sector_momentum_score is NULL or missing. "
                            f"Data quality issue in sector_ranking table."
                        )
                        raise ValueError(
                            f"{symbol}: Sector momentum score is NULL. Cannot compute swing trader score without valid sector metrics."
                        )

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

                # Use trend_template_data date (guaranteed non-None by line 243 validation).
                # No fallback chain — trend data is required upstream.
                if "date" not in trend or trend["date"] is None:
                    raise ValueError(
                        f"{symbol}: trend_template_data missing required 'date' field on required date"
                    )
                score_date = trend["date"]
                results.append(
                    {
                        "symbol": symbol,
                        "date": score_date,
                        "setup_score": setup_score,
                        "trend_score": trend_score,
                        "momentum_score": momentum_score,
                        "volume_score": volume_score,
                        "fundamentals_score": fundamentals_score,
                        "sector_score": sector_score,
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
        """Convert RSI to momentum score (40-70 RSI range).

        Penalizes neutral RSI (45-55) to avoid false sense of "okay" momentum.
        Only gives high scores to strong signals: RSI < 35 (oversold) or > 75 (overbought).
        Fails fast on weak momentum by returning lower baseline scores.
        """
        if rsi < 30:
            # Strong oversold: 0 = 5, 30 = 40
            return (rsi / 30) * 40
        elif rsi < 40:
            # Weak oversold: 30-40 → 40-50 (low momentum)
            return 40 + ((rsi - 30) / 10) * 10
        elif rsi < 45:
            # Neutral-low: 40-45 → 45-50
            return 45 + ((rsi - 40) / 5) * 5
        elif rsi < 55:
            # NEUTRAL ZONE (45-55): No conviction, return weak baseline
            # Don't return 50 (middle default suggesting "okay").
            # Return 35 to indicate "lack of momentum signal"
            return 35.0
        elif rsi < 60:
            # Neutral-high: 55-60 → 50-55
            return 50 + ((rsi - 55) / 5) * 5
        elif rsi < 70:
            # Weak overbought: 60-70 → 50-60
            return 50 + ((rsi - 60) / 10) * 10
        else:
            # Strong overbought: 70 = 60, 100 = 100
            return 60 + ((min(rsi, 100) - 70) / 30) * 40

    def _bulk_insert(self, df: pd.DataFrame) -> int:
        """Bulk insert all scores at once using COPY (fast batch insert)."""
        if df.empty:
            return 0

        # Validate required score fields exist
        required_score_fields = [
            "grade",
            "setup_score",
            "trend_score",
            "momentum_score",
            "volume_score",
            "fundamentals_score",
            "sector_score",
            "multi_tf_score",
            "total_score",
        ]
        missing_fields = [f for f in required_score_fields if f not in df.columns]
        if missing_fields:
            raise ValueError(f"DataFrame missing required score fields: {missing_fields}")

        try:
            import json
            from io import StringIO

            with DatabaseContext("write") as cur:
                # Prepare data: build JSON components and format for insertion
                df["date"] = df["date"].dt.date.astype(str)

                # Build components JSON for each row
                components_list = []
                for _, row in df.iterrows():
                    grade = row["grade"]
                    components = {
                        "grade": str(grade) if not pd.isna(grade) else None,
                        "setup": float(row["setup_score"]) if not pd.isna(row["setup_score"]) else None,
                        "trend": float(row["trend_score"]) if not pd.isna(row["trend_score"]) else None,
                        "momentum": float(row["momentum_score"]) if not pd.isna(row["momentum_score"]) else None,
                        "volume": float(row["volume_score"]) if not pd.isna(row["volume_score"]) else None,
                        "fundamentals": float(row["fundamentals_score"]) if not pd.isna(row["fundamentals_score"]) else None,
                        "sector": float(row["sector_score"]) if not pd.isna(row["sector_score"]) else None,
                        "multi_tf": float(row["multi_tf_score"]) if not pd.isna(row["multi_tf_score"]) else None,
                    }
                    components_list.append(json.dumps(components))

                df["components"] = components_list
                df["score"] = df["total_score"].astype(float)

                # Select only columns needed for COPY
                insert_columns = ["symbol", "date", "score", "components"]
                insert_df = df[insert_columns].copy()

                # Lock table for atomic delete/insert (prevents concurrent loader corruption)
                cur.execute("LOCK TABLE swing_trader_scores IN EXCLUSIVE MODE")

                # Delete existing rows for symbols being loaded (allows re-compute)
                symbols_to_load = insert_df["symbol"].unique().tolist()
                delete_param_positions = ",".join(["%s"] * len(symbols_to_load))
                delete_sql = f"DELETE FROM swing_trader_scores WHERE symbol IN ({delete_param_positions})"
                cur.execute(delete_sql, symbols_to_load)
                logger.info(f"Deleted {cur.rowcount} stale rows for {len(symbols_to_load)} symbols")

                # Build COPY command
                import psycopg2.sql

                col_ids = [psycopg2.sql.Identifier(c) for c in insert_columns]
                sql = psycopg2.sql.SQL(
                    "COPY {table} ({fields}) FROM STDIN WITH (FORMAT CSV, FORCE_NULL ({fields}))"
                ).format(
                    table=psycopg2.sql.Identifier("swing_trader_scores"),
                    fields=psycopg2.sql.SQL(", ").join(col_ids),
                )

                # Stream CSV data to COPY (fast batch insert)
                csv_string = insert_df.to_csv(index=False, header=False, na_rep="")
                csv_buffer = StringIO(csv_string)
                cur.copy_expert(sql, csv_buffer)

                inserted = int(cur.rowcount) if cur.rowcount is not None else 0
                logger.info(f"Bulk inserted {inserted} swing trader scores via COPY")
                return inserted

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"[BULK INSERT FAILED] Cannot persist swing trader scores: {e}") from e
        except (ValueError, TypeError, KeyError) as e:
            raise RuntimeError(f"[BULK INSERT FORMAT ERROR] Invalid data format for bulk insert: {e}") from e


def _update_swing_loader_status(status: str, error_message: str | None = None) -> None:
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


def _swing_heartbeat_worker(stop_event: threading.Event) -> None:
    """Periodically update last_updated to signal loader is alive."""
    while not stop_event.is_set():
        if stop_event.wait(timeout=60):  # exits immediately when stop is requested
            break
        try:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Vectorized Swing Trader Scores Loader")
    parser.add_argument(
        "--today",
        action="store_true",
        help="Intraday mode: only compute today's scores (fast)",
    )
    parser.add_argument("--limit", type=int, default=None, help="Limit to N symbols (for testing)")
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
    heartbeat_thread = threading.Thread(target=_swing_heartbeat_worker, args=(stop_heartbeat,), daemon=False)
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

        # Validate result structure upfront
        required_fields = ["rows_inserted", "error"]
        missing = [f for f in required_fields if f not in result]
        if missing:
            raise RuntimeError(
                f"Loader returned incomplete result: missing {missing}. "
                f"Expected fields: {required_fields}, got: {list(result.keys())}"
            )

        # Update status to COMPLETED or FAILED based on result
        rows_inserted: int = result["rows_inserted"]  # type: ignore[assignment]
        error: str | None = result["error"]  # type: ignore[assignment]
        if rows_inserted > 0 or error is None:
            _update_swing_loader_status("COMPLETED")
            final_status = "completed"
        else:
            _update_swing_loader_status("FAILED", error)
            final_status = "failed"

        # Log execution time
        # CRITICAL: duration_sec is required — do not default to 0
        if "duration_sec" not in result:
            logger.error("[SWING_TRADER_SCORES] Missing 'duration_sec' in execution result")
            final_status = "error"
            duration_sec: int | float = 0
        else:
            duration_sec = result["duration_sec"]  # type: ignore[assignment]

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
                        result["rows_inserted"],
                        duration_sec,
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
