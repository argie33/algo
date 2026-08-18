#!/usr/bin/env python3
"""Technical Data Daily Loader - Vectorized for Institutional Speed

Computes technical indicators (SMA, Bollinger Bands, RSI, MACD, ATR, ADX) for ALL symbols.
Also consolidates VCP (Volatility Contraction Pattern) calculation from separate loader.
Uses vectorized bulk operations (10-20x faster than per-symbol approach):
- Single bulk fetch of all price_daily data
- Vectorized pandas operations across all 5000+ symbols
- Single bulk insert for all results + VCP patterns
- Completes in 15-25 minutes vs 60-90 minutes with per-symbol approach

This is the primary/only implementation; per-symbol variants were deprecated.

Run: python3 loaders/load_technical_data_daily.py [--limit 100]
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

from loaders.technical_indicators import (
    compute_adx,
    compute_atr,
    compute_bollinger_bands,
    compute_macd,
    compute_moving_averages,
    compute_rsi,
    compute_volume_ma,
    detect_and_adjust_splits,
)
from utils.data.age_validator import DataAgeValidator
from utils.db.context import DatabaseContext
from utils.db.retry import OptimisticLockRetry
from utils.infrastructure.timezone import EASTERN_TZ
from utils.loaders.helpers import get_active_symbols
from utils.loaders.status_manager import LoaderStatusManager
from utils.type_conversion import safe_float

logger = logging.getLogger(__name__)

# _compute_all_indicators_vectorized fetches ~400 calendar days of price history per symbol
# (252 trading days for roc_252d plus MA/RSI warmup buffer) but only writes the most recent
# this-many days to technical_indicators - see both usages below.
OUTPUT_WINDOW_DAYS_TECH_INDICATORS = 30


class VectorizedTechnicalLoader:
    """Institutional-grade loader: fetch all data once, compute all at once."""

    def __init__(self) -> None:
        self.table_name = "technical_data_daily"
        self.vcp_patterns_inserted = 0
        self.skipped_symbols_count = 0

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

        # CRITICAL FIX: Skip loading on non-trading days
        # Markets are closed on weekends/holidays, so no new price data is available
        # Loaders should not fail just because it's Saturday - that's expected behavior
        from algo.infrastructure import MarketCalendar

        if not MarketCalendar.is_trading_day(end_date):
            logger.info(
                f"[TECHNICAL_DATA] Skipping load: today ({end_date}) is not a trading day. "
                f"Technical indicators will use last available trading day's data."
            )
            return {
                "rows_inserted": 0,
                "latest_date": None,
                "error": None,
                "data_available": True,
                "duration_sec": time.time() - start_time,
            }

        # 252-trading-day indicators (roc_252d) need ~252 * 7/5 ≈ 353 calendar days of
        # history plus market holidays; 300 was short by ~50+ days and left roc_252d
        # (and therefore minervini_trend_score, which sums it) permanently NULL.
        start_date = end_date - timedelta(days=400)

        logger.info(f"VectorizedTechnicalLoader: {len(symbols)} symbols, date range {start_date} to {end_date}")

        try:
            # Validate upstream price data freshness before computing indicators
            # Technical indicators require fresh price data to be accurate
            # Do NOT fall back to stale data - fail-fast enforcement
            price_freshness = DataAgeValidator.check("price_daily")
            if not price_freshness["is_fresh"]:
                # CRITICAL FIX (Session 416): Raise RuntimeError, not ValueError, for data layer failures.
                # Per GOVERNANCE.md line 24-25: "Type errors from mypy... raise RuntimeError"
                # ValueError is for user input/content validation; RuntimeError is for system layer failures.
                # Data validator schema mismatch is a system failure, not invalid input.
                threshold_days = price_freshness.get("threshold_days")
                if threshold_days is None:
                    logger.critical(
                        f"[TECHNICAL_DATA CRITICAL] Data validator schema mismatch. "
                        f"Freshness check result missing required 'threshold_days' field. "
                        f"DataAgeValidator may have been modified incorrectly. Result: {price_freshness}"
                    )
                    raise RuntimeError(
                        "[TECHNICAL_DATA CRITICAL] Data validation layer schema mismatch. "
                        "Cannot proceed with technical indicator computation. "
                        "Fix: Verify DataAgeValidator.check() returns threshold_days field."
                    ) from None
                raise RuntimeError(
                    f"[TECHNICAL_DATA CRITICAL] Cannot compute technical indicators with stale price data. "
                    f"Price data is {price_freshness['age_days']} days old (threshold {threshold_days} days). "
                    f"Message: {price_freshness['message']}. "
                    f"Fix: Ensure price_daily loader completed successfully with fresh data."
                )

            all_prices = self._fetch_all_prices(symbols, start_date, end_date)
            if not all_prices:
                raise RuntimeError(
                    f"[PRICES] No price data found for {len(symbols)} symbols in date range "
                    f"{start_date} to {end_date}. Cannot compute technical indicators without price data."
                )

            logger.info(f"Fetched {len(all_prices)} price rows across {len(symbols)} symbols")

            indicators_df = self._compute_all_indicators_vectorized(all_prices)

            logger.info(f"Computed indicators: {len(indicators_df)} rows")

            if indicators_df.empty:
                raise RuntimeError(
                    "[TECHNICAL] Indicators dataframe is empty after computation. "
                    "This indicates vectorized computation failed or produced no valid indicator values. "
                    "Check upstream price data and indicator calculation functions."
                )

            # Incremental write: indicators are COMPUTED over the full 400-day window (the
            # lookback is required for 252d ROC etc.), but only rows newer than each symbol's
            # existing technical_data_daily watermark (minus a 7-day healing overlap) are
            # WRITTEN. Previously the entire ~250-day x ~5000-symbol frame (~1.3-2.7M rows)
            # was upserted every run, twice a day, with ~99% value-identical no-op updates
            # churning indexes and dead tuples. New symbols (no watermark) get full history.
            # Explicit --since/INTRADAY_MODE takes precedence; TECH_FULL_REFRESH=true forces
            # a full-window rewrite for recovery/backfill.
            write_df = indicators_df
            if since_date is None and os.getenv("TECH_FULL_REFRESH", "").lower() not in ("true", "1", "yes"):
                write_df = self._filter_to_unloaded_rows(indicators_df)

            inserted = self._bulk_insert(write_df, since_date)

            # CRITICAL: Populate minervini_trend_score from trend_template_data (computed by load_trend_analysis.py)
            # Stock scores need momentum (minervini_trend_score) to compute composite scores
            # If trend_template_data not yet available, this gracefully adds NULL (expected on timing mismatches)
            self._populate_minervini_scores()

            # RE-ENABLED 2026-07-20: was disabled because the per-symbol implementation did
            # 3 DB round trips/symbol (~30K queries, 60s+ timeout). Rewritten to compute
            # entirely from the in-memory indicators_df (zero additional DB queries) - see
            # _compute_and_insert_vcp_patterns/_compute_vcp_for_symbol. vcp_patterns had gone
            # 23+ days stale with this disabled, and load_signal_quality_scores.py hard-fails
            # once a symbol's VCP lookback window has zero rows.
            self._compute_and_insert_vcp_patterns(indicators_df)

            # Get the latest date in the computed indicators
            latest_date = None
            if len(indicators_df) > 0:
                latest_date = indicators_df["date"].max()

            duration = time.time() - start_time
            logger.info(
                f"VectorizedTechnicalLoader completed: {inserted} technical rows, "
                f"{self.vcp_patterns_inserted} VCP patterns in {duration:.1f}s, latest_date={latest_date}"
            )

            return {
                "symbols_processed": len(symbols),
                # Real per-run completion count (attempted minus symbols skipped for data
                # quality reasons inside _compute_all_indicators_vectorized), not an echo of
                # the attempted count - see that method's skipped_symbols_count comment.
                "symbols_loaded": len(symbols) - self.skipped_symbols_count,
                "rows_inserted": inserted,
                "vcp_patterns_inserted": self.vcp_patterns_inserted,
                "duration_sec": round(duration, 2),
                "latest_date": latest_date,
                "error": None,
                "data_available": True,  # Indicators computed successfully
            }

        except RuntimeError as e:
            logger.error(f"VectorizedTechnicalLoader failed: {e}", exc_info=True)
            return {
                "symbols_processed": 0,
                "rows_inserted": 0,
                "duration_sec": round(time.time() - start_time, 2),
                "error": str(e),
                "latest_date": None,
                "data_available": False,  # Computation failed - no indicators available
            }
        except Exception as e:
            logger.error(f"VectorizedTechnicalLoader unexpected error: {e}", exc_info=True)
            return {
                "symbols_processed": 0,
                "rows_inserted": 0,
                "duration_sec": round(time.time() - start_time, 2),
                "error": f"Unexpected error: {e!s}",
                "latest_date": None,
                "data_available": False,  # Unexpected error - no indicators available
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
        return safe_float(duration, "duration_sec", allow_none=False)

    # A single query for the whole universe (10k+ symbols x 400 days) keeps a
    # transaction open long enough that a transient RDS Proxy SSL drop discards the
    # entire fetch; chunking bounds each round trip's blast radius and lets retries
    # redo one batch instead of the whole universe.
    _FETCH_BATCH_SIZE = 1000

    def _fetch_price_batch(self, symbols: list[str], start_date: date, end_date: date) -> list[Any]:
        with DatabaseContext("read") as cur:
            sql_param_markers = ",".join(["%s"] * len(symbols))
            query = f"""
                SELECT symbol, date, open, high, low, close, volume
                FROM price_daily
                WHERE symbol IN ({sql_param_markers})
                AND date >= %s AND date <= %s
                ORDER BY symbol, date ASC
            """
            cur.execute(query, [*symbols, start_date, end_date])
            return cast(list[Any], cur.fetchall())

    def _fetch_all_prices(self, symbols: list[str], start_date: date, end_date: date) -> list[dict[str, Any]]:
        """Fetch ALL price data in symbol-batched queries (institutional-scale efficiency).

        Instead of: FOR each symbol, fetch its prices (5000 queries)
        We do: SELECT prices WHERE symbol IN (batch of 1000) (~11 queries for 10k symbols)

        Batching keeps each query fast enough to avoid transient RDS Proxy SSL drops,
        and retry_on_exception re-fetches only the failed batch, not the whole universe.
        """
        try:
            rows: list[Any] = []
            for i in range(0, len(symbols), self._FETCH_BATCH_SIZE):
                batch = symbols[i : i + self._FETCH_BATCH_SIZE]

                def fetch_batch(b: list[str] = batch) -> list[Any]:
                    return self._fetch_price_batch(b, start_date, end_date)

                batch_rows = OptimisticLockRetry.retry_on_exception(
                    fetch_batch,
                    operation_name="technical_data_daily.fetch_price_batch",
                    max_attempts=3,
                    context={"batch_start": i, "batch_size": len(batch)},
                )
                # GOVERNANCE: Fail-fast on data fetch failure - no silent fallback to empty list
                if batch_rows is None:
                    raise RuntimeError(
                        f"[PRICE_BATCH_FETCH] Failed to fetch price batch starting at index {i} "
                        f"(size {len(batch)}) after 3 retries. Cannot compute technical indicators "
                        f"without complete price data."
                    )
                rows.extend(batch_rows)

            # Convert to list of dicts for easier processing
            result = []
            for r in rows:
                close = safe_float(r[5], f"price_daily.close[{r[0]}]", allow_none=True)
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
                        "open": safe_float(r[2], f"price_daily.open[{r[0]}]", allow_none=True),
                        "high": safe_float(r[3], f"price_daily.high[{r[0]}]", allow_none=True),
                        "low": safe_float(r[4], f"price_daily.low[{r[0]}]", allow_none=True),
                        "close": close,
                        "volume": volume,
                    }
                )

            # HIGH FIX #2: Validate coverage - fail if upstream data incomplete
            if not result:
                raise RuntimeError(
                    f"No price data found for {len(symbols)} symbols in date range [{start_date}, {end_date}]. "
                    f"price_daily loader may have failed or data is stale."
                )

            # Check coverage: at least 80% of symbols have data
            symbols_with_data = {r["symbol"] for r in result}
            coverage_ratio = len(symbols_with_data) / len(symbols)
            if coverage_ratio < 0.8:
                missing_symbols = set(symbols) - symbols_with_data
                logger.error(
                    f"[COVERAGE] price_daily coverage only {coverage_ratio * 100:.1f}% ({len(symbols_with_data)}/{len(symbols)} symbols). "
                    f"Missing: {sorted(missing_symbols)[:10]}... "
                    f"This indicates upstream price_daily loader failed partially."
                )
                raise RuntimeError(
                    f"Insufficient price data coverage ({coverage_ratio * 100:.1f}%). "
                    f"Cannot compute indicators - upstream price_daily must be >80% complete."
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

        # Pre-fetch SPY prices once for the full date range - cached for all symbols.
        # Previously fetched per-symbol (10,635 DB queries). Now fetched once.
        all_dates = df["date"]
        spy_prices_cached = self._fetch_spy_prices(all_dates.min().date(), all_dates.max().date())

        results = []

        skipped_symbols = []
        for symbol in df["symbol"].unique():
            symbol_df = df[df["symbol"] == symbol].sort_values("date").reset_index(drop=True)
            # In-memory only: price_daily stores raw/unadjusted prices, so a stock split
            # inside this symbol's history would otherwise read as a fake ~50%+ single-day
            # move that corrupts every indicator below (RSI/MACD/MAs/ATR/Bollinger/ROC) for
            # up to 252 days. Does not write back to price_daily. See
            # loaders/technical_indicators.py::detect_and_adjust_splits for the full story.
            symbol_df = detect_and_adjust_splits(symbol_df)

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

                # Validate ROC values fit within database NUMERIC(14,4) precision (-99999.9999 to 99999.9999)
                # Extreme volatility (e.g., stock dropping 50% in 1 day = -5000% ROC) should NOT crash entire loader
                # Instead: skip this symbol, log alert, continue with others
                # This prevents one micro-cap stock meltdown from breaking technical indicators for 5000 symbols
                #
                # OUTPUT-WINDOW FIX (2026-08-17, live-reproduced via reference_then_morning_after_signals.log -
                # 20+ symbols/run hitting this): symbol_df here spans the full ~400-day fetch window (400 =
                # 252 trading days for roc_252d + buffer), but only the last 30 days (OUTPUT_WINDOW_DAYS below,
                # matching the `date >= now - 30 days` trim later in this function) are ever written to
                # technical_indicators - everything older is pure MA/RSI/ROC warmup. The original check ran
                # over the FULL window and skipped the entire symbol - including its otherwise-valid CURRENT
                # indicators - whenever ANY single day anywhere in the ~370 days of warmup-only history had an
                # extreme ROC (a real but long-past crash/reorg/bad tick), even though that day was never going
                # to be written to the DB either way. Now only an exceeded value that falls inside the actual
                # output window forces a skip; a warmup-only outlier is clipped like any other in-range warmup
                # value (clipping a value that's never persisted can't corrupt real output - it only exists to
                # keep pandas' rolling-window math from choking on it) and processing continues normally.
                roc_max = 99999.9999
                output_window_start = datetime.now(EASTERN_TZ).date() - timedelta(
                    days=OUTPUT_WINDOW_DAYS_TECH_INDICATORS
                )
                for col in [
                    "roc",
                    "roc_10d",
                    "roc_20d",
                    "roc_60d",
                    "roc_120d",
                    "roc_252d",
                ]:
                    before = symbol_df[col].copy()
                    exceeded_values = before[before.abs() > roc_max]

                    if len(exceeded_values) > 0:
                        exceeded_dates = symbol_df.loc[exceeded_values.index, "date"].dt.date
                        in_output_window = exceeded_dates >= output_window_start
                        max_exceeded = exceeded_values.abs().max()

                        if in_output_window.any():
                            logger.critical(
                                f"[ROC_OVERFLOW_SKIP] {symbol}: {int(in_output_window.sum())} {col} values within "
                                f"the {OUTPUT_WINDOW_DAYS_TECH_INDICATORS}-day output window exceed NUMERIC(14,4) "
                                f"range. Max value: {max_exceeded:.4f}. Skipping this symbol to prevent loader crash. "
                                f"This indicates extreme micro-cap volatility (possibly delisted/bankrupt security). "
                                f"Examples: {exceeded_values.head(3).values}"
                            )
                            skipped_symbols.append(symbol)
                            raise RuntimeError(f"[ROC_OVERFLOW_SKIP] {symbol}: extreme volatility detected")

                        logger.warning(
                            f"[ROC_OVERFLOW_CLIP] {symbol}: {len(exceeded_values)} {col} values exceed "
                            f"NUMERIC(14,4) range, all outside the {OUTPUT_WINDOW_DAYS_TECH_INDICATORS}-day output "
                            f"window (warmup-only history, never persisted). Max value: {max_exceeded:.4f}. "
                            f"Clipping and continuing - does not affect any written row."
                        )

                    # Clipping is OK for values within safe range (defensive programming) and for
                    # warmup-only exceeded values handled above (never written to the DB).
                    symbol_df[col] = symbol_df[col].clip(-roc_max, roc_max)

                # Moving averages
                mas = compute_moving_averages(symbol_df["close"])
                for name, values in mas.items():
                    symbol_df[name] = values

                # ATR & ADX
                symbol_df["atr_14"] = compute_atr(symbol_df["high"], symbol_df["low"], symbol_df["close"], 14)
                symbol_df["atr_50"] = compute_atr(symbol_df["high"], symbol_df["low"], symbol_df["close"], 50)
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

                # Mansfield RS (SPY comparison) - optional; NaN if SPY unavailable or insufficient history
                import numpy as np

                try:
                    if not spy_prices_cached:
                        raise RuntimeError(
                            f"[MANSFIELD_RS] SPY price data unavailable for {symbol}. "
                            f"Mansfield relative strength is critical for trend analysis and cannot be computed without current SPY data. "
                            f"Ensure SPY prices are loaded before computing technical indicators."
                        )

                    spy_df = pd.DataFrame(spy_prices_cached)
                    spy_df["date"] = pd.to_datetime(spy_df["date"])
                    spy_closes = spy_df.set_index("date")["close"]

                    if (spy_closes == 0).any() or spy_closes.isna().all():
                        raise RuntimeError(
                            f"[MANSFIELD_RS] SPY price data invalid for {symbol}: contains zeros or all NaN. "
                            f"Cannot compute relative strength with invalid price data."
                        )

                    target_index = pd.DatetimeIndex(symbol_df["date"].values)
                    spy_aligned = spy_closes.reindex(target_index)

                    # Only fail if stock dates are missing from SPY; SPY having extra dates is fine
                    missing_count = spy_aligned.isna().sum()
                    if missing_count > 0:
                        missing_pct = 100.0 * missing_count / len(spy_aligned)
                        if missing_pct > 10:
                            # More than 10% of dates missing: likely data quality issue
                            raise RuntimeError(
                                f"[MANSFIELD_RS] SPY price data incomplete for {symbol}: {missing_pct:.1f}% of dates missing. "
                                f"Cannot compute relative strength without adequate SPY alignment."
                            )
                        else:
                            # < 10% missing: use forward-fill for continuity
                            spy_aligned = spy_aligned.ffill()
                            if spy_aligned.isna().any():
                                # If ffill didn't work, use bfill as fallback
                                spy_aligned = spy_aligned.bfill()
                                # CRITICAL: Validate that bfill actually filled the gaps
                                if spy_aligned.isna().any():
                                    remaining_nans = spy_aligned.isna().sum()
                                    raise RuntimeError(
                                        f"[MANSFIELD_RS] SPY alignment failed for {symbol}: "
                                        f"ffill+bfill left {remaining_nans} NaN values. "
                                        f"Cannot compute relative strength with missing SPY prices. "
                                        f"Reason: possibly all-NaN period at start/end of data range."
                                    )

                    rs_line = symbol_df["close"].values / spy_aligned.values
                    rs_line_s = pd.Series(rs_line, index=symbol_df.index)
                    rs_line_s = rs_line_s.replace([np.inf, -np.inf], np.nan)

                    rs_line_52w_ma = rs_line_s.rolling(window=252, min_periods=126).mean()

                    if rs_line_52w_ma.isna().all():
                        raise RuntimeError(
                            f"[MANSFIELD_RS] Insufficient data history for {symbol}: need 126+ days for rolling mean. "
                            f"Cannot compute relative strength trend without adequate historical data."
                        )

                    mansfield_result = (rs_line_s / rs_line_52w_ma - 1) * 100
                    mansfield_result = mansfield_result.replace([np.inf, -np.inf], np.nan)
                    symbol_df["mansfield_rs"] = mansfield_result
                except RuntimeError as _mansfield_err:
                    # Mansfield RS is a useful but non-critical metric. Allow NULL and continue.
                    # Downstream should NOT mark entire symbol as unavailable if this metric fails.
                    logger.warning(
                        f"[MANSFIELD_RS DEGRADATION] {symbol}: {_mansfield_err}. "
                        f"Mansfield RS will be NULL for this symbol/date. "
                        f"This is acceptable - symbol still has other technical indicators."
                    )
                    symbol_df["mansfield_rs"] = np.nan

                # Format for insertion
                symbol_df["price_data_age_days"] = 0  # Mark as current

                # Keep only rows after warmup period (skip first 300 days used for MA computation)
                symbol_df = symbol_df[symbol_df["date"].dt.date >= output_window_start]

                results.append(symbol_df)

            except RuntimeError as e:
                error_str = str(e)
                if "ROC_OVERFLOW_SKIP" in error_str:
                    logger.warning(f"[INDICATORS] Skipping {symbol} due to extreme ROC values")
                    continue
                raise RuntimeError(
                    f"[INDICATORS] Failed to compute indicators for {symbol}: {e}. "
                    "Data may be corrupted or have invalid format."
                ) from e
            except (ValueError, TypeError, KeyError, ZeroDivisionError) as e:
                raise RuntimeError(
                    f"[INDICATORS] Failed to compute indicators for {symbol}: {e}. "
                    "Data may be corrupted or have invalid format."
                ) from e

        # Report skipped symbols for audit trail
        # FIX 2026-08-10: this count used to be logged and then discarded - run()'s
        # completion status always reported symbols_processed=len(symbols) (the attempted
        # input count, not how many actually got indicator rows), so mark_completed()'s
        # safety check had no real per-run signal to fall back on and DB-verified as frozen
        # at the exact same "10549/10549" across 12+ consecutive runs. Stashing this on the
        # instance lets run() report a real completed-vs-attempted count.
        self.skipped_symbols_count = len(skipped_symbols)
        if skipped_symbols:
            logger.warning(
                f"[INDICATORS] {len(skipped_symbols)} symbols skipped due to data quality issues "
                f"(extreme ROC values, insufficient price data, etc): {skipped_symbols[:10]}"
                + (f"... and {len(skipped_symbols) - 10} more" if len(skipped_symbols) > 10 else "")
            )

        if not results:
            return pd.DataFrame()

        return pd.concat(results, ignore_index=True)

    def _fetch_spy_prices(self, start_date: date, end_date: date) -> list[dict[str, Any]]:
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT date, close FROM price_daily WHERE symbol = %s AND date >= %s AND date <= %s ORDER BY date ASC",
                    ("SPY", start_date, end_date),
                )
                return [
                    {"date": r[0], "close": safe_float(r[1], f"SPY.close[{r[0]}]", allow_none=True)}
                    for r in cur.fetchall()
                ]
        except psycopg2.Error as e:
            raise RuntimeError(
                f"[SPY_PRICES] Failed to fetch SPY prices for Mansfield RS [{start_date} to {end_date}]: {e}. "
                "Cannot compute relative strength indicator."
            ) from e
        except (ValueError, TypeError) as e:
            raise RuntimeError(
                f"[SPY_PRICES] Invalid SPY price data format: {e}. SPY price data may be corrupted."
            ) from e

    def _compute_and_insert_vcp_patterns(self, indicators_df: pd.DataFrame) -> None:
        """Compute VCP patterns from indicators and insert to vcp_patterns table.

        Consolidation: Previously in separate load_vcp_patterns.py loader.
        VCP patterns depend on ATR which we just computed, so consolidate here for efficiency.

        VECTORIZED (re-enabled): the previous per-symbol implementation issued 3 DB round
        trips per symbol (ATR history + current volume + average volume) - ~30K queries
        across the ~10K-symbol universe, 60s+ and the reason this was disabled outright
        (see git history). `indicators_df` already carries each symbol's full fetched price
        history (close/high/low/volume) plus the atr_14 this same run just computed from it
        - there is no need to re-fetch any of that from the DB a second time per symbol.

        Args:
            indicators_df: DataFrame with computed technical indicators including atr_14
                and volume, one row per symbol per date (full fetched history, not just
                the latest day).
        """
        if indicators_df.empty or "atr_14" not in indicators_df.columns:
            logger.warning("[VCP] No indicators or ATR data available - skipping VCP pattern computation")
            return

        if "volume" not in indicators_df.columns:
            logger.warning("[VCP] No volume data available - skipping VCP pattern computation")
            return

        try:
            vcp_patterns: list[dict[str, Any]] = []
            failed_symbols = []

            for symbol, symbol_df in indicators_df.groupby("symbol"):
                try:
                    self._compute_vcp_for_symbol(symbol, symbol_df, vcp_patterns)
                except Exception as e:
                    # GOVERNANCE: Log at WARNING level (not DEBUG) for visibility to operators
                    logger.warning(f"[VCP] Failed to compute VCP for {symbol}: {e}")
                    failed_symbols.append(symbol)

            if vcp_patterns:
                self._bulk_insert_vcp_patterns(vcp_patterns)
                if failed_symbols:
                    logger.warning(
                        f"[VCP] Partial success: {len(vcp_patterns)} patterns computed, {len(failed_symbols)} symbols failed: {failed_symbols[:10]}"
                    )
            else:
                logger.warning("[VCP] No VCP patterns computed - all symbols failed or empty indicators")
        except Exception as e:
            logger.error(f"[VCP] VCP pattern computation failed (non-blocking): {e}")

    def _compute_vcp_for_symbol(self, symbol: str, symbol_df: pd.DataFrame, vcp_patterns: list[dict[str, Any]]) -> None:
        """Compute VCP pattern for a single symbol from its in-memory indicator history.

        No DB queries - `symbol_df` is this symbol's slice of `indicators_df`, already
        containing the full fetched price/indicator history for the run.

        Args:
            symbol: Stock symbol
            symbol_df: This symbol's rows from indicators_df (date, atr_14, volume, ...)
            vcp_patterns: List to append results to
        """
        df = symbol_df.sort_values("date")
        atr_hist = df[df["atr_14"].notna()]

        # NOTE: the original standalone load_vcp_patterns.py (pre-consolidation) only
        # required *any* ATR history (`if not rows: raise`), not a specific count - the
        # consolidated version's `len(atr_rows) < 30` guard required 30 rows within a
        # 30-*calendar*-day window, which a 5-day trading week can basically never satisfy
        # (~21-22 trading days per 30 calendar days) and made every symbol return early
        # even before this was fully disabled. Restore the original's "average whatever
        # history is available" behavior instead of re-introducing that dead guard.
        if atr_hist.empty:
            return

        last_30 = atr_hist.tail(30)
        current_row = last_30.iloc[-1]
        current_atr = safe_float(current_row["atr_14"], f"{symbol}.atr_current", allow_none=False)
        atr_30d_avg = float(last_30["atr_14"].mean())

        if not atr_30d_avg:
            return

        atr_compression_pct = max(0, (1.0 - (current_atr / atr_30d_avg)) * 100)
        vcp_strength = min(100, max(0, int(atr_compression_pct)))

        end_date = current_row["date"]
        # numpy.int64 (volume's dtype) doesn't pass safe_float's `isinstance(value, int)`
        # check (unlike numpy.float64, which subclasses Python float) - cast explicitly
        # instead of routing a pandas-native numeric through a validator built for
        # DB-row/JSON-shaped inputs.
        current_vol_raw = current_row.get("volume")
        current_vol = float(current_vol_raw) if current_vol_raw is not None and pd.notna(current_vol_raw) else None

        # 30 calendar days strictly before the current row, volume > 0 - matches the
        # original per-symbol query's window and filter exactly.
        window_start = end_date - timedelta(days=30)
        prior = df[(df["date"] < end_date) & (df["date"] >= window_start) & (df["volume"] > 0)]
        avg_vol_raw = float(prior["volume"].mean()) if not prior.empty else None
        avg_vol = avg_vol_raw if avg_vol_raw and avg_vol_raw == avg_vol_raw else None  # drop None/NaN

        # Previously defaulted missing current_vol/avg_vol to a fabricated 1.0, which silently
        # produced a nonsense ratio (e.g. real_vol/1.0) indistinguishable from a genuine reading.
        # Leave the ratio NULL when either side of the ratio isn't real.
        breakout_volume_ratio = (
            current_vol / avg_vol if current_vol is not None and avg_vol is not None and avg_vol > 0 else None
        )

        # Daily high-low range as % of close, matching atr_compression_pct's percentage
        # convention. Previously hardcoded to 0.0 (unconditionally, not even a fallback) despite
        # real high/low/close data being in scope on symbol_df.
        current_close = safe_float(current_row.get("close"), f"{symbol}.range_current_close", allow_none=True)
        current_high = safe_float(current_row.get("high"), f"{symbol}.range_current_high", allow_none=True)
        current_low = safe_float(current_row.get("low"), f"{symbol}.range_current_low", allow_none=True)
        range_current = (
            (current_high - current_low) / current_close * 100
            if current_close and current_high is not None and current_low is not None
            else None
        )

        range_hist = last_30.assign(_range_pct=lambda d: (d["high"] - d["low"]) / d["close"].replace(0, pd.NA) * 100)[
            "_range_pct"
        ].dropna()
        range_30d_avg = float(range_hist.mean()) if not range_hist.empty else None

        vcp_patterns.append(
            {
                "symbol": symbol,
                "date": end_date.date() if hasattr(end_date, "date") else end_date,
                "atr_30d_avg": atr_30d_avg,
                "atr_current": current_atr,
                "atr_compression_pct": atr_compression_pct,
                "range_30d_avg": range_30d_avg,
                "range_current": range_current,
                "vcp_strength": vcp_strength,
                "breakout_volume_ratio": breakout_volume_ratio,
            }
        )

    def _bulk_insert_vcp_patterns(self, vcp_patterns: list[dict[str, Any]]) -> None:
        """Insert VCP patterns to database using COPY.

        Args:
            vcp_patterns: List of VCP pattern dicts
        """
        if not vcp_patterns:
            return

        try:
            vcp_df = pd.DataFrame(vcp_patterns)
            columns = [
                "symbol",
                "date",
                "atr_30d_avg",
                "atr_current",
                "atr_compression_pct",
                "range_30d_avg",
                "range_current",
                "vcp_strength",
                "breakout_volume_ratio",
            ]

            vcp_df["date"] = pd.to_datetime(vcp_df["date"]).dt.date.astype(str)

            with DatabaseContext("write") as cur:
                cur.execute("LOCK TABLE vcp_patterns IN EXCLUSIVE MODE")

                # Clear old VCP patterns for symbols being loaded
                symbols_to_load = vcp_df["symbol"].unique().tolist()
                sql_param_markers = ",".join(["%s"] * len(symbols_to_load))
                delete_sql = f"DELETE FROM vcp_patterns WHERE symbol IN ({sql_param_markers})"
                cur.execute(delete_sql, symbols_to_load)

                # Insert new patterns
                import psycopg2.sql

                col_ids = [psycopg2.sql.Identifier(c) for c in columns]
                sql = psycopg2.sql.SQL(
                    "COPY {table} ({fields}) FROM STDIN WITH (FORMAT CSV, FORCE_NULL ({fields}))"
                ).format(
                    table=psycopg2.sql.Identifier("vcp_patterns"),
                    fields=psycopg2.sql.SQL(", ").join(col_ids),
                )

                csv_string = vcp_df[columns].to_csv(index=False, header=False, na_rep="")
                csv_buffer = StringIO(csv_string)
                cur.copy_expert(sql, csv_buffer)

                self.vcp_patterns_inserted = cast(int, cur.rowcount)
                logger.info(f"[VCP] Inserted {self.vcp_patterns_inserted} VCP patterns")
        except Exception as e:
            logger.error(f"[VCP] Failed to insert VCP patterns: {e}")
            raise

    def _filter_to_unloaded_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        """Drop rows already present in technical_data_daily (per-symbol watermark filter).

        Keeps rows dated within 7 days of (or after) each symbol's current MAX(date) so
        late price corrections still heal, and ALL rows for symbols with no existing data.
        Fails safe: any problem reading watermarks, or an unexpectedly empty result, falls
        back to writing the full frame (the pre-existing behavior).
        """
        try:
            with DatabaseContext("read") as cur:
                cur.execute("SELECT symbol, MAX(date) FROM technical_data_daily GROUP BY symbol")
                watermarks = {row[0]: row[1] for row in cur.fetchall()}
        except psycopg2.Error as e:
            logger.warning(f"[INCREMENTAL] Watermark read failed ({e}); falling back to full-window write")
            return df

        if not watermarks:
            logger.info("[INCREMENTAL] technical_data_daily is empty - writing full window")
            return df

        overlap = pd.Timedelta(days=7)
        symbol_watermark = pd.to_datetime(df["symbol"].map(watermarks))
        keep = symbol_watermark.isna() | (df["date"] >= symbol_watermark - overlap)
        kept = df[keep]
        if kept.empty:
            logger.warning(
                "[INCREMENTAL] Watermark filter removed every row (unexpected); falling back to full-window write"
            )
            return df
        logger.info(
            f"[INCREMENTAL] Writing {len(kept)}/{len(df)} rows "
            f"({len(df) - len(kept)} already loaded, 7-day overlap retained for healing)"
        )
        return kept

    def _bulk_insert(self, df: pd.DataFrame, since_date: date | None = None) -> int:
        """Bulk insert all indicators at once using COPY (fast).

        Returns:
            Number of rows inserted. Returns 0 only if dataframe is empty (no indicators computed).

        Raises:
            RuntimeError: If database operation fails
        """
        if df.empty:
            raise RuntimeError(
                "[TECHNICAL] Cannot bulk insert empty indicator dataframe. "
                "This should have been caught by caller. "
                "Indicates programming error or upstream data validation failure."
            )

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
            "atr_50",
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
            "data_unavailable",
            "reason",
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

        # Add data quality columns
        # data_unavailable: FALSE when load succeeds, reason: NULL
        df["data_unavailable"] = False
        df["reason"] = None

        # Handle NaN -> None conversion for non-integer columns
        for col in df.columns:
            if col not in ("symbol", "date") and col not in integer_cols and col not in ("data_unavailable",):
                df[col] = df[col].where(pd.notna(df[col]), None)

        # Bulk insert via temp table + UPSERT (atomic, no table locking)
        # FIX: Changed from DELETE+EXCLUSIVE_LOCK+INSERT to temp table + UPSERT
        # Benefits: atomic per row, concurrent-safe, no table-level locking
        try:
            with DatabaseContext("write") as cur:
                insert_df = df[columns]

                # Step 1: Create temp table with new data
                import psycopg2.sql

                col_ids = [psycopg2.sql.Identifier(c) for c in columns]
                col_defs = []
                for col in columns:
                    # Infer types from dataframe
                    dtype = insert_df[col].dtype
                    if col in ("symbol",):
                        pg_type = "VARCHAR(20)"
                    elif col in ("date",):
                        pg_type = "DATE"
                    elif col in ("data_unavailable",):
                        pg_type = "BOOLEAN"
                    elif col in ("reason",):
                        pg_type = "TEXT"
                    elif dtype in ("int64", "Int64"):
                        pg_type = "BIGINT"
                    elif dtype in ("float64",):
                        pg_type = "NUMERIC"
                    else:
                        pg_type = "NUMERIC"
                    col_defs.append(f"{col} {pg_type}")

                # Create temp table
                temp_table_sql = f"CREATE TEMP TABLE technical_data_daily_new ({', '.join(col_defs)})"
                cur.execute(temp_table_sql)

                # Step 2: Load data into temp table via COPY
                col_ids = [psycopg2.sql.Identifier(c) for c in columns]
                copy_sql = psycopg2.sql.SQL(
                    "COPY {table} ({fields}) FROM STDIN WITH (FORMAT CSV, FORCE_NULL ({fields}))"
                ).format(
                    table=psycopg2.sql.Identifier("technical_data_daily_new"),
                    fields=psycopg2.sql.SQL(", ").join(col_ids),
                )
                csv_string = insert_df.to_csv(index=False, header=False, na_rep="")
                csv_buffer = StringIO(csv_string)
                cur.copy_expert(copy_sql, csv_buffer)
                logger.info(f"Loaded {cur.rowcount} rows into temp table")

                # Step 3: UPSERT from temp table to main table (atomic, no locks)
                update_cols = [col for col in columns if col not in ("symbol", "date")]
                update_set = ", ".join([f"{col} = EXCLUDED.{col}" for col in update_cols])

                upsert_sql = f"""
                    INSERT INTO technical_data_daily ({", ".join(columns)})
                    SELECT {", ".join(columns)} FROM technical_data_daily_new
                    ON CONFLICT (symbol, date) DO UPDATE SET {update_set}
                """
                cur.execute(upsert_sql)
                inserted = cast(int, cur.rowcount)
                logger.info(f"Upserted {inserted} technical indicator rows from temp table")

                # Temp table auto-dropped at end of session
                return inserted

        except psycopg2.Error as e:
            raise RuntimeError(
                f"[BULK_INSERT] Failed to insert technical indicators: {e}. Database connectivity or permissions issue."
            ) from e
        except (ValueError, TypeError, KeyError) as e:
            raise RuntimeError(
                f"[BULK_INSERT] Invalid data format for bulk insert: {e}. Data structure mismatch with schema."
            ) from e

    def _populate_minervini_scores(self) -> None:
        """Populate minervini_trend_score in technical_data_daily from trend_template_data.

        CRITICAL: Stock scores need minervini_trend_score (momentum) to compute composite scores.
        trend_template_data is computed by load_trend_analysis.py and contains minervini_trend_score.
        This method JOINs the values and updates technical_data_daily.

        If trend_template_data doesn't have data yet (timing mismatch), this is non-fatal
        (stocks will be marked unavailable in stock_scores due to insufficient metrics).
        """
        try:
            with DatabaseContext("write") as cur:
                # Update technical_data_daily with minervini_trend_score from trend_template_data
                # This JOIN will only populate rows where both tables have matching symbol/date
                cur.execute("""
                    UPDATE technical_data_daily
                    SET minervini_trend_score = t.minervini_trend_score
                    FROM trend_template_data t
                    WHERE technical_data_daily.symbol = t.symbol
                    AND technical_data_daily.date = t.date
                    AND technical_data_daily.minervini_trend_score IS NULL
                    """)
                updated = cur.rowcount
                if updated > 0:
                    logger.info(
                        f"[MINERVINI] Populated {updated} rows with minervini_trend_score from trend_template_data"
                    )
                else:
                    logger.debug(
                        "[MINERVINI] No minervini scores to populate (trend_template_data may not be ready yet)"
                    )
        except psycopg2.Error as e:
            logger.warning(
                f"[MINERVINI] Failed to populate minervini_trend_score (non-fatal): {e}. "
                f"Stock scores will mark affected symbols unavailable due to insufficient metrics."
            )


def _update_tech_loader_status(
    status: str,
    error_message: str | None = None,
    latest_date: date | None = None,
    execution_duration_sec: float | None = None,
    current_run_symbol_count: int | None = None,
    current_run_symbols_loaded: int | None = None,
) -> None:
    # Use LoaderStatusManager for centralized status updates (RACE CONDITION FIX)
    # Map old status values to LoaderStatusManager methods
    status_mgr = LoaderStatusManager("technical_data_daily")

    if status == "RUNNING":
        status_mgr.mark_running()
    elif status == "COMPLETED":
        # FIX 2026-08-10: previously never passed current_run_* here, so mark_completed()'s
        # <98%-completion safety check fell back to whatever symbol_count/symbols_loaded was
        # last in the DB row - a value this loader itself never wrote with real per-run data.
        # DB-verified: data_loader_status_history showed the identical "10549/10549" frozen
        # across 12+ consecutive runs. Passing this run's real attempted/completed counts
        # (from VectorizedTechnicalLoader.run()'s symbols_processed/symbols_loaded) lets the
        # safety check actually see a partial-failure run instead of a stale echo.
        status_mgr.mark_completed(
            latest_date=latest_date,
            execution_duration_sec=execution_duration_sec,
            current_run_symbol_count=current_run_symbol_count,
            current_run_symbols_loaded=current_run_symbols_loaded,
        )
    elif status == "FAILED":
        status_mgr.mark_failed(error_message=error_message or "Unknown error")
    else:
        raise ValueError(
            f"[TECHNICAL_INDICATORS] Invalid status '{status}'. "
            f"Must be one of: RUNNING, COMPLETED, FAILED. "
            f"Unexpected status could corrupt data_loader_status. Fail-fast to prevent data corruption."
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
            # Use LoaderStatusManager for centralized heartbeat (RACE CONDITION FIX)
            status_mgr = LoaderStatusManager("technical_data_daily")
            status_mgr.update_progress()  # Just update last_updated
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.critical(
                f"HEARTBEAT FAILURE: Cannot update loader status - hung task detection DISABLED. "
                f"Loader may hang without external detection. Database: {type(e).__name__}: {str(e)[:100]}"
            )


def _apply_schema_migrations() -> None:
    """Add columns that were missing from initial schema deployment."""
    migrations = [
        "ALTER TABLE technical_data_daily ADD COLUMN IF NOT EXISTS atr_50 DECIMAL(12, 4)",
        "ALTER TABLE technical_data_daily ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE",
        "ALTER TABLE technical_data_daily ADD COLUMN IF NOT EXISTS reason VARCHAR(500)",
    ]
    try:
        with DatabaseContext("write") as cur:
            for sql in migrations:
                cur.execute(sql)
    except Exception as e:
        logger.warning(f"Schema migration failed (non-fatal, will retry next run): {e}")


def main() -> int:
    """Vectorized Technical Data Loader.

    Exit codes: 0=success, 1=error, 2=no_data
    """
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

    # Apply any pending schema migrations before running
    _apply_schema_migrations()

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
            logger.error(f"Failed to get symbols (DB error): {e}", exc_info=True)
            _update_tech_loader_status("FAILED", f"Symbol fetch failed: {e!s}")
            return 1
        except Exception as e:
            logger.error(f"Failed to get symbols (unexpected error): {e}", exc_info=True)
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
        required_fields = ["rows_inserted", "error", "latest_date", "data_available"]
        missing = [f for f in required_fields if f not in result]
        if missing:
            raise RuntimeError(
                f"Loader returned incomplete result: missing {missing}. "
                f"Expected fields: {required_fields}, got: {list(result.keys())}"
            )

        # Validate data_available is explicit boolean (never implicit)
        if not isinstance(result["data_available"], bool):
            raise RuntimeError(
                f"[VALIDATION] data_available must be explicit boolean, got {type(result['data_available']).__name__}: "
                f"{result['data_available']!r}. Cannot proceed with ambiguous data availability."
            )

        # Cross-validate error and data_available consistency
        if not result["data_available"] and result["error"] is None:
            raise RuntimeError(
                "[VALIDATION] Inconsistent result: data_available=False but error=None. "
                "When data is unavailable, error must contain failure reason."
            )
        if result["data_available"] and result["error"] is not None:
            raise RuntimeError(
                "[VALIDATION] Inconsistent result: data_available=True but error is set. "
                "Cannot have both successful computation and error state."
            )

        # Update status to COMPLETED or FAILED based on result
        if result["rows_inserted"] > 0:
            _update_tech_loader_status(
                "COMPLETED",
                latest_date=result["latest_date"],
                execution_duration_sec=result.get("duration_sec"),
                current_run_symbol_count=result.get("symbols_processed"),
                current_run_symbols_loaded=result.get("symbols_loaded"),
            )
            final_status = "completed"
            exit_code = 0
        elif not result["data_available"] and result["error"] is None:
            # Data unavailable (market closed, etc) - this is NO_DATA, not an error
            # BUG FOUND live 2026-08-16: the skip-path result dict never carries
            # "symbols_processed"/"symbols_loaded" keys, so result.get(...) returned None
            # for both, and mark_completed() (via _update_tech_loader_status) fell back to
            # re-reading symbol_count/symbols_loaded from the DB row - which mark_running()
            # had just reset to (len(symbols), 0) at the start of THIS run. That read as
            # "0/4922 loaded (0.00%)", tripped the <98%-completion safety check, and got
            # silently overridden to FAILED even though skipping was the correct behavior.
            # Pass explicit counts so a legitimate no-op skip reads as 100% complete, not 0%.
            _update_tech_loader_status(
                "COMPLETED",
                latest_date=result["latest_date"],
                execution_duration_sec=result.get("duration_sec"),
                current_run_symbol_count=result.get("symbols_processed", len(symbols)),
                current_run_symbols_loaded=result.get("symbols_loaded", len(symbols)),
            )
            final_status = "no_data"
            exit_code = 2
            logger.info("[LOADER] Technical data unavailable (market closed?). Exit code 2 (NO_DATA).")
        elif result["rows_inserted"] == 0 and result["data_available"] and result["error"] is None:
            # No new rows but data available (non-trading day, or already cached)
            # This is normal and expected - market data isn't changing when market is closed
            # Same fallback-to-stale-zeroed-row bug as the branch above - see comment there.
            _update_tech_loader_status(
                "COMPLETED",
                latest_date=result["latest_date"],
                execution_duration_sec=result.get("duration_sec"),
                current_run_symbol_count=result.get("symbols_processed", len(symbols)),
                current_run_symbols_loaded=result.get("symbols_loaded", len(symbols)),
            )
            final_status = "completed"
            exit_code = 0
            logger.info("[LOADER] No new technical data to load (market closed or data already cached). Exit code 0.")
        else:
            _update_tech_loader_status("FAILED", result["error"])
            final_status = "failed"
            exit_code = 1

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

        return exit_code

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"Unexpected error in main: {e}", exc_info=True)
        _update_tech_loader_status("FAILED", f"Unexpected error: {e!s}")
        return 1
    finally:
        # Stop heartbeat thread and wait for clean shutdown
        stop_heartbeat.set()
        heartbeat_thread.join(timeout=15)
        if heartbeat_thread.is_alive():
            logger.error("Heartbeat thread still running after 15s timeout - may be hung in database operation")
            # Non-daemon threads will block process exit until they finish
            # This log entry flags the issue for monitoring/alerts


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    sys.exit(main())
