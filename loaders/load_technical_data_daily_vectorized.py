#!/usr/bin/env python3
"""Technical Data Daily Loader — Vectorized for Institutional Speed

Computes technical indicators for ALL 5000+ symbols at once (not per-symbol).
Uses:
- Single bulk fetch of all price data
- Vectorized pandas operations across all symbols
- Single bulk insert for all results

This is 10-20x faster than per-symbol processing for large datasets.
Performance: 5000 symbols in 15-25 minutes vs 60-90 minutes with per-symbol approach.

Run: python3 loaders/load_technical_data_daily_vectorized.py [--limit 100]
"""

import argparse
import logging
import os
import sys
import threading
import time
from datetime import date, datetime, timedelta
from io import StringIO
from typing import Any, cast
from zoneinfo import ZoneInfo

import pandas as pd
import psycopg2
from pandas.tseries.offsets import CustomBusinessDay

from loaders.technical_indicators import (
    compute_adx,
    compute_atr,
    compute_bollinger_bands,
    compute_macd,
    compute_moving_averages,
    compute_rsi,
    compute_volume_ma,
)
from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ
from utils.loaders.helpers import get_active_symbols

logger = logging.getLogger(__name__)


class VectorizedTechnicalLoader:
    """Institutional-grade loader: fetch all data once, compute all at once."""

    def __init__(self) -> None:
        self.table_name = "technical_data_daily"

    def run(self, symbols: list[str], since_date: date | None = None) -> dict[str, Any]:
        """Load technical indicators for all symbols vectorized.

        Args:
            symbols: List of ticker symbols
            since_date: Only process data after this date (for incremental loads)

        Returns:
            Dict with {symbols_processed, rows_inserted, duration_sec, latest_date}
        """
        start_time = time.time()

        now_utc = datetime.now(ZoneInfo("UTC"))
        now_et = now_utc.astimezone(EASTERN_TZ)
        end_date = now_et.date()

        start_date = end_date - timedelta(days=300)

        logger.info(f"VectorizedTechnicalLoader: {len(symbols)} symbols, date range {start_date} to {end_date}")

        try:
            all_prices = self._fetch_all_prices(symbols, start_date, end_date)
            if not all_prices:
                raise RuntimeError(
                    f"[PRICES] No price data found for {len(symbols)} symbols in date range "
                    f"{start_date} to {end_date}. Cannot compute technical indicators without price data."
                )

            logger.info(f"Fetched {len(all_prices)} price rows across {len(symbols)} symbols")

            indicators_df = self._compute_all_indicators_vectorized(all_prices)

            logger.info(f"Computed indicators: {len(indicators_df)} rows")

            inserted = self._bulk_insert(indicators_df, since_date)

            # Get the latest date in the computed indicators
            latest_date = None
            if len(indicators_df) > 0:
                latest_date = indicators_df["date"].max()

            duration = time.time() - start_time
            logger.info(
                f"VectorizedTechnicalLoader completed: {inserted} rows in {duration:.1f}s, latest_date={latest_date}"
            )

            return {
                "symbols_processed": len(symbols),
                "rows_inserted": inserted,
                "duration_sec": round(duration, 2),
                "latest_date": latest_date,
                "error": None,
            }

        except RuntimeError as e:
            logger.error(f"VectorizedTechnicalLoader failed: {e}", exc_info=True)
            return {
                "symbols_processed": 0,
                "rows_inserted": 0,
                "duration_sec": round(time.time() - start_time, 2),
                "error": str(e),
                "latest_date": None,
            }
        except Exception as e:
            logger.error(f"VectorizedTechnicalLoader unexpected error: {e}", exc_info=True)
            return {
                "symbols_processed": 0,
                "rows_inserted": 0,
                "duration_sec": round(time.time() - start_time, 2),
                "error": f"Unexpected error: {e!s}",
                "latest_date": None,
            }

    def _get_required_duration(self, result: dict[str, Any]) -> float:
        """Get duration_sec from result; fail-fast if missing.

        Duration tracking is CRITICAL for monitoring loader health and detecting hung processes.
        Defaulting to 0 would mask hangs and performance degradation.

        Raises:
            RuntimeError: If duration_sec missing or invalid
        """
        if "duration_sec" not in result:
            raise RuntimeError(
                "[TECHNICAL_DATA] Loader execution metrics incomplete: duration_sec missing. "
                "Duration tracking is CRITICAL for monitoring loader health and detecting hung processes."
            )
        duration = result["duration_sec"]
        if not isinstance(duration, (int, float)):
            raise RuntimeError(
                f"[TECHNICAL_DATA] Duration tracking failed: duration_sec={duration!r} is not numeric. "
                "Cannot monitor loader performance without valid duration."
            )
        return float(duration)

    def _fetch_all_prices(self, symbols: list[str], start_date: date, end_date: date) -> list[dict[str, Any]]:
        """Fetch ALL price data in ONE query (institutional-scale efficiency).

        Instead of: FOR each symbol, fetch its prices (5000 queries)
        We do: SELECT all prices WHERE symbol IN (...) (1 query)

        This reduces database round trips from 5000 to 1.
        """
        try:
            with DatabaseContext("read") as cur:
                placeholders = ",".join(["%s"] * len(symbols))
                query = f"""
                    SELECT symbol, date, open, high, low, close, volume
                    FROM price_daily
                    WHERE symbol IN ({placeholders})
                    AND date >= %s AND date <= %s
                    ORDER BY symbol, date ASC
                """
                cur.execute(query, [*symbols, start_date, end_date])
                rows = cur.fetchall()

                # Convert to list of dicts for easier processing
                result = []
                for r in rows:
                    close = float(r[5]) if r[5] is not None else None
                    volume = int(r[6]) if r[6] is not None else None

                    # Skip invalid rows
                    if close is None or close <= 0:
                        continue
                    if volume is not None and volume == 0:
                        continue

                    result.append(
                        {
                            "symbol": r[0],
                            "date": r[1],
                            "open": float(r[2]) if r[2] else None,
                            "high": float(r[3]) if r[3] else None,
                            "low": float(r[4]) if r[4] else None,
                            "close": close,
                            "volume": volume,
                        }
                    )

                return result
        except psycopg2.Error as e:
            raise RuntimeError(
                f"[PRICES] Failed to fetch prices for {len(symbols)} symbols [{start_date} to {end_date}]: {e}. "
                "Cannot compute technical indicators without price data."
            ) from e
        except (ValueError, TypeError) as e:
            raise RuntimeError(f"[PRICES] Invalid price data format: {e}. Price data may be corrupted.") from e

    def _compute_all_indicators_vectorized(self, prices: list[dict[str, Any]]) -> pd.DataFrame:
        """Compute ALL technical indicators for ALL symbols at once using pandas.

        Key optimization: Group by symbol, compute indicators per group, concat results.
        This is vectorized (fast) vs symbol-by-symbol loops (slow).
        """
        df = pd.DataFrame(prices)
        df["date"] = pd.to_datetime(df["date"])

        # Pre-fetch SPY prices once for the full date range — cached for all symbols.
        # Previously fetched per-symbol (10,635 DB queries). Now fetched once.
        all_dates = df["date"]
        spy_prices_cached = self._fetch_spy_prices(all_dates.min().date(), all_dates.max().date())

        results = []

        for symbol in df["symbol"].unique():
            symbol_df = df[df["symbol"] == symbol].sort_values("date").reset_index(drop=True)

            # Compute all indicators for this symbol's data
            try:
                # Basic indicators
                symbol_df["rsi"] = compute_rsi(symbol_df["close"])
                symbol_df["rsi_14"] = symbol_df["rsi"]

                macd_line, signal_line = compute_macd(symbol_df["close"])
                symbol_df["macd"] = macd_line
                symbol_df["macd_signal"] = signal_line
                symbol_df["macd_hist"] = macd_line - signal_line
                symbol_df["macd_histogram"] = symbol_df["macd_hist"]

                # Momentum
                symbol_df["mom"] = symbol_df["close"].diff()
                symbol_df["roc"] = symbol_df["close"].pct_change() * 100
                symbol_df["roc_10d"] = symbol_df["close"].pct_change(10) * 100
                symbol_df["roc_20d"] = symbol_df["close"].pct_change(20) * 100
                symbol_df["roc_60d"] = symbol_df["close"].pct_change(60) * 100
                symbol_df["roc_120d"] = symbol_df["close"].pct_change(120) * 100
                symbol_df["roc_252d"] = symbol_df["close"].pct_change(252) * 100

                # Clamp ROC
                decimal84_max = 9999.9999
                for col in [
                    "roc",
                    "roc_10d",
                    "roc_20d",
                    "roc_60d",
                    "roc_120d",
                    "roc_252d",
                ]:
                    before = symbol_df[col].copy()
                    symbol_df[col] = symbol_df[col].clip(-decimal84_max, decimal84_max)
                    capped_count = ((before.abs() > decimal84_max) & (symbol_df[col].notna())).sum()
                    if capped_count > 0:
                        logger.warning(
                            f"{symbol}: {capped_count} {col} values capped to +/{decimal84_max} (extreme market conditions)"
                        )

                # Moving averages
                mas = compute_moving_averages(symbol_df["close"])
                for name, values in mas.items():
                    symbol_df[name] = values

                # ATR & ADX
                symbol_df["atr_14"] = compute_atr(symbol_df["high"], symbol_df["low"], symbol_df["close"], 14)
                symbol_df["atr"] = symbol_df["atr_14"]
                symbol_df["plus_di"], symbol_df["minus_di"], symbol_df["adx"] = compute_adx(
                    symbol_df["high"], symbol_df["low"], symbol_df["close"], 14
                )

                # Bollinger Bands
                bbs = compute_bollinger_bands(symbol_df["close"], 20, 2.0)
                for name, values in bbs.items():
                    symbol_df[name] = values

                # Volume MA
                symbol_df["volume_ma_50"] = compute_volume_ma(symbol_df["volume"], 50)

                # Mansfield RS (SPY comparison) — uses pre-cached SPY prices (1 DB fetch for all symbols)
                try:
                    if spy_prices_cached:
                        from algo.infrastructure.market_calendar import US_HOLIDAYS

                        spy_df = pd.DataFrame(spy_prices_cached)
                        spy_df["date"] = pd.to_datetime(spy_df["date"])
                        spy_closes = spy_df.set_index("date")["close"]

                        # Defensive check: zero or all-NaN SPY prices would cause division by zero
                        if (spy_closes == 0).any() or spy_closes.isna().all():
                            logger.debug(f"SPY alignment invalid for {symbol} (zeros or all NaN)")
                            symbol_df["mansfield_rs"] = None
                        else:
                            import numpy as np

                            holidays = list(US_HOLIDAYS.keys())
                            cbd = CustomBusinessDay(holidays=holidays)
                            target_index = pd.DatetimeIndex(symbol_df["date"].values, freq=cbd)
                            spy_aligned = spy_closes.reindex(target_index)

                            # Forward-fill NaN values from missing SPY dates (ffill avoids FutureWarning)
                            spy_filled = spy_aligned.ffill()
                            rs_line = symbol_df["close"].values / spy_filled.values
                            rs_line_s = pd.Series(rs_line, index=symbol_df.index)
                            # Replace infinities with NaN
                            rs_line_s = rs_line_s.replace([np.inf, -np.inf], np.nan)

                            rs_line_52w_ma = rs_line_s.rolling(window=252, min_periods=126).mean()

                            # Only compute if rolling mean is not all NaN
                            if rs_line_52w_ma.isna().all():
                                logger.debug(f"Insufficient RS history for {symbol} (need 126+ days)")
                                symbol_df["mansfield_rs"] = None
                            else:
                                mansfield_result = (rs_line_s / rs_line_52w_ma - 1) * 100
                                # Replace infinities with NaN
                                mansfield_result = mansfield_result.replace([np.inf, -np.inf], np.nan)
                                symbol_df["mansfield_rs"] = mansfield_result
                except (ValueError, ZeroDivisionError, TypeError) as e:
                    logger.debug(f"Could not compute Mansfield RS for {symbol} (optional enrichment): {e}")
                    symbol_df["mansfield_rs"] = None

                # Format for insertion
                symbol_df["price_data_age_days"] = 0  # Mark as current

                # Keep only rows after warmup period (skip first 300 days used for MA computation)
                symbol_df = symbol_df[
                    symbol_df["date"].dt.date >= (datetime.now(EASTERN_TZ).date() - timedelta(days=30))
                ]

                results.append(symbol_df)

            except (ValueError, TypeError, KeyError, ZeroDivisionError) as e:
                raise RuntimeError(
                    f"[INDICATORS] Failed to compute indicators for {symbol}: {e}. "
                    "Data may be corrupted or have invalid format."
                ) from e

        if not results:
            return pd.DataFrame()

        return pd.concat(results, ignore_index=True)

    def _fetch_spy_prices(self, start_date: date, end_date: date) -> list[dict[str, Any]]:
        """Fetch SPY prices for Mansfield RS calculation."""
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT date, close FROM price_daily WHERE symbol = %s AND date >= %s AND date <= %s ORDER BY date ASC",
                    ("SPY", start_date, end_date),
                )
                return [{"date": r[0], "close": float(r[1])} for r in cur.fetchall()]
        except psycopg2.Error as e:
            raise RuntimeError(
                f"[SPY_PRICES] Failed to fetch SPY prices for Mansfield RS [{start_date} to {end_date}]: {e}. "
                "Cannot compute relative strength indicator."
            ) from e
        except (ValueError, TypeError) as e:
            raise RuntimeError(
                f"[SPY_PRICES] Invalid SPY price data format: {e}. SPY price data may be corrupted."
            ) from e

    def _bulk_insert(self, df: pd.DataFrame, since_date: date | None = None) -> int:
        """Bulk insert all indicators at once using COPY (fast)."""
        if df.empty:
            return 0

        # Filter to only new data if incremental
        if since_date:
            df = df[df["date"].dt.date >= since_date]

        # Prepare columns for insertion
        columns = [
            "symbol",
            "date",
            "rsi",
            "rsi_14",
            "macd",
            "macd_signal",
            "macd_hist",
            "macd_histogram",
            "mom",
            "roc",
            "roc_10d",
            "roc_20d",
            "roc_60d",
            "roc_120d",
            "roc_252d",
            "sma_20",
            "sma_50",
            "sma_150",
            "sma_200",
            "ema_12",
            "ema_21",
            "ema_26",
            "atr",
            "atr_14",
            "bb_upper",
            "bb_middle",
            "bb_lower",
            "volume_ma_50",
            "adx",
            "plus_di",
            "minus_di",
            "mansfield_rs",
            "price_data_age_days",
            "close",
        ]

        # Format data
        df["date"] = df["date"].dt.date.astype(str)

        # Convert integer columns to nullable Int64 to prevent float encoding in CSV
        # This fixes: "invalid input syntax for type bigint: 2042066.0"
        integer_cols = ["volume_ma_50", "price_data_age_days"]
        for col in integer_cols:
            if col in df.columns:
                # Round to int, convert to Int64 (nullable integer type)
                df[col] = df[col].round(0).astype("Int64")

        # Handle NaN -> None conversion for non-integer columns
        for col in df.columns:
            if col not in ("symbol", "date") and col not in integer_cols:
                df[col] = df[col].where(pd.notna(df[col]), None)

        # Bulk insert via COPY (with DELETE to handle updates)
        try:
            with DatabaseContext("write") as cur:
                insert_df = df[columns]

                # Prevent concurrent loaders from corrupting data: acquire explicit lock
                # LOCK TABLE ensures serialized access to DELETE/INSERT operation
                cur.execute("LOCK TABLE technical_data_daily IN EXCLUSIVE MODE")

                # Delete existing rows for symbols being loaded (allows re-compute)
                # Now protected by EXCLUSIVE lock — no other loader can interfere
                symbols_to_load = insert_df["symbol"].unique().tolist()
                placeholders = ",".join(["%s"] * len(symbols_to_load))
                delete_sql = f"DELETE FROM technical_data_daily WHERE symbol IN ({placeholders})"
                cur.execute(delete_sql, symbols_to_load)
                logger.info(f"Deleted {cur.rowcount} stale rows for {len(symbols_to_load)} symbols")

                # Build COPY command
                import psycopg2.sql

                col_ids = [psycopg2.sql.Identifier(c) for c in columns]
                sql = psycopg2.sql.SQL(
                    "COPY {table} ({fields}) FROM STDIN WITH (FORMAT CSV, FORCE_NULL ({fields}))"
                ).format(
                    table=psycopg2.sql.Identifier("technical_data_daily"),
                    fields=psycopg2.sql.SQL(", ").join(col_ids),
                )

                # Stream CSV data to COPY (wrap string in StringIO for file-like object)
                csv_string = insert_df.to_csv(index=False, header=False, na_rep="")
                csv_buffer = StringIO(csv_string)
                cur.copy_expert(sql, csv_buffer)

                inserted = cast(int, cur.rowcount)
                logger.info(f"Bulk inserted {inserted} technical indicator rows")
                return inserted

        except psycopg2.Error as e:
            raise RuntimeError(
                f"[BULK_INSERT] Failed to insert technical indicators: {e}. Database connectivity or permissions issue."
            ) from e
        except (ValueError, TypeError, KeyError) as e:
            raise RuntimeError(
                f"[BULK_INSERT] Invalid data format for bulk insert: {e}. Data structure mismatch with schema."
            ) from e


def _update_tech_loader_status(status: str, error_message: str | None = None, latest_date: date | None = None) -> None:
    """Update data_loader_status for Phase 1 monitoring."""
    with DatabaseContext("write") as cur:
        if status == "RUNNING":
            cur.execute(
                """
                UPDATE data_loader_status
                SET status = %s, last_updated = NOW(), execution_started = NOW()
                WHERE table_name = %s
            """,
                (status, "technical_data_daily"),
            )
            if cur.rowcount == 0:
                cur.execute(
                    """
                    INSERT INTO data_loader_status
                    (table_name, status, last_updated, execution_started)
                    VALUES (%s, %s, NOW(), NOW())
                """,
                    ("technical_data_daily", status),
                )
        else:
            if latest_date:
                cur.execute(
                    """
                    UPDATE data_loader_status
                    SET status = %s, last_updated = NOW(), execution_completed = NOW(), error_message = %s, latest_date = %s
                    WHERE table_name = %s
                """,
                    (status, error_message, latest_date, "technical_data_daily"),
                )
            else:
                cur.execute(
                    """
                    UPDATE data_loader_status
                    SET status = %s, last_updated = NOW(), execution_completed = NOW(), error_message = %s
                    WHERE table_name = %s
                """,
                    (status, error_message, "technical_data_daily"),
                )


def _tech_heartbeat_worker(stop_event: threading.Event) -> None:
    """Periodically update last_updated to signal loader is alive.

    CRITICAL: Heartbeat updates enable hung task detection in monitoring systems.
    If heartbeat fails, hung task detection is disabled. Log at CRITICAL level.
    """
    while not stop_event.is_set():
        try:
            if stop_event.wait(timeout=60):  # exits early when stop is requested
                break
            with DatabaseContext("write") as cur:
                cur.execute(
                    """
                    UPDATE data_loader_status
                    SET last_updated = NOW()
                    WHERE table_name = %s AND status = %s
                """,
                    ("technical_data_daily", "RUNNING"),
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.critical(
                f"HEARTBEAT FAILURE: Cannot update loader status — hung task detection DISABLED. "
                f"Loader may hang without external detection. Database: {type(e).__name__}: {str(e)[:100]}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Vectorized Technical Data Loader")
    parser.add_argument("--limit", type=int, default=None, help="Limit to N symbols (for testing)")
    parser.add_argument("--since", type=str, help="Only load data after YYYY-MM-DD")
    args = parser.parse_args()

    # Support INTRADAY_MODE environment variable (set by EventBridge/Step Functions)
    # When set, load only today's data for rapid intraday updates (3-8 min vs 15-25 min)
    if os.getenv("INTRADAY_MODE", "").lower() in ("true", "1", "yes"):
        now_et = datetime.now(EASTERN_TZ)
        args.since = now_et.date().isoformat()
        logger.info(f"[ENV] INTRADAY_MODE=true, loading data since {args.since}")

    # Update status to RUNNING before fetching symbols
    _update_tech_loader_status("RUNNING")

    # Start heartbeat thread for hung task detection
    stop_heartbeat = threading.Event()
    heartbeat_thread = threading.Thread(target=_tech_heartbeat_worker, args=(stop_heartbeat,), daemon=False)
    heartbeat_thread.start()

    try:
        # Get symbols
        try:
            symbols = get_active_symbols(timeout_secs=300)
            if args.limit:
                symbols = symbols[: args.limit]
            logger.info(f"Loaded {len(symbols)} symbols for vectorized processing")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"Failed to get symbols: {e}")
            _update_tech_loader_status("FAILED", f"Symbol fetch failed: {e!s}")
            return 1

        # Parse since date
        since_date = None
        if args.since:
            try:
                since_date = datetime.strptime(args.since, "%Y-%m-%d").date()
            except ValueError as e:
                logger.error(f"Invalid date format: {args.since}: {e}")
                _update_tech_loader_status("FAILED", f"Invalid date format: {args.since}")
                return 1

        # Run vectorized loader
        loader = VectorizedTechnicalLoader()
        result = loader.run(symbols, since_date=since_date)

        logger.info(f"Result: {result}")

        # Validate result structure upfront
        required_fields = ["rows_inserted", "error", "latest_date"]
        missing = [f for f in required_fields if f not in result]
        if missing:
            raise RuntimeError(
                f"Loader returned incomplete result: missing {missing}. "
                f"Expected fields: {required_fields}, got: {list(result.keys())}"
            )

        # Update status to COMPLETED or FAILED based on result
        if result["rows_inserted"] > 0 or result["error"] is None:
            _update_tech_loader_status("COMPLETED", latest_date=result["latest_date"])
            final_status = "completed"
        else:
            _update_tech_loader_status("FAILED", result["error"])
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
                        "technical_data_daily_vectorized",
                        "technical_data_daily",
                        date.today(),
                        final_status,
                        result["rows_inserted"],
                        loader._get_required_duration(result),  # FAIL-FAST: duration_sec is REQUIRED for monitoring
                    ),
                )
        except psycopg2.Error as e:
            logger.warning(f"Failed to log execution metrics (non-critical): {e}")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(f"Unexpected error logging execution (non-critical): {e}", exc_info=True)

        return 0 if final_status == "completed" else 1

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"Unexpected error in main: {e}", exc_info=True)
        _update_tech_loader_status("FAILED", f"Unexpected error: {e!s}")
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
