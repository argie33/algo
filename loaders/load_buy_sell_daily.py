#!/usr/bin/env python3
"""Daily buy/sell signals generator.

Generates daily trading signals from technical indicators and quality scores.
Populates the buy_sell_daily table.
"""

import sys

from loaders.loader_helper import setup_imports

setup_imports()

import argparse
import logging
from datetime import date, datetime, timedelta
from typing import Any

import psycopg2

from algo.signals.buy_signal_generator import BuySignalGenerator
from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ
from utils.loaders.config import get_default_parallelism
from utils.loaders.helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class SignalsDailyLoader(OptimalLoader):
    """Daily signals loader that generates buy/sell signals from technical indicators."""

    table_name = "buy_sell_daily"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def _prepare_batch_context(self) -> None:
        """Load shared data once to avoid N+1 queries (ROOT CAUSE #4 FIX).

        Queries that depend on end_date, not symbol:
        - How many symbols have prices on the target date (denominator for completeness check)
        - How many symbols have technical data on the target date (coverage check)

        Instead of querying these 10,506 times (once per symbol), query them once
        and cache in _batch_context.

        BUGFIX: Use the most recent date with actual price_daily data, not the market calendar date.
        Market calendar can say a date is a trading day but data hasn't been loaded yet.
        """
        from datetime import datetime, timezone

        from algo.infrastructure import MarketCalendar

        self._batch_context = {}
        try:
            now_utc = datetime.now(timezone.utc)
            now_et = now_utc.astimezone(EASTERN_TZ)
            end = now_et.date()

            # CLUSTER 4 FIX: Use cached is_trading_day() to prevent repeated lookups
            # The @lru_cache on _is_trading_day_cached() makes repeated checks ~1000x faster
            max_iterations = 10  # Prevent infinite loop (max gap is ~3 days over a weekend)
            iterations = 0
            while end > date(2020, 1, 1) and not MarketCalendar.is_trading_day(end) and iterations < max_iterations:
                end = end - timedelta(days=1)
                iterations += 1

            with DatabaseContext("read") as cur:
                # Find most recent date with COMPLETE price_daily coverage (>= 3000 symbols)
                # If today's price_daily is incomplete (partial load), fall back to yesterday
                # This allows buy_sell_daily to run with the most recent complete data set
                # instead of blocking on incomplete intra-day loads
                cur.execute(
                    """SELECT date, COUNT(DISTINCT symbol) as cnt
                       FROM price_daily
                       WHERE date <= %s
                       GROUP BY date
                       ORDER BY date DESC
                       LIMIT 10""",
                    (end,),
                )
                complete_date_rows = cur.fetchall()

                # Find the most recent date with >= 3000 symbols
                end = None
                price_coverage_symbols = 0
                if complete_date_rows:
                    for row in complete_date_rows:
                        if row[1] >= 3000:
                            end = row[0]
                            price_coverage_symbols = int(row[1])
                            logger.info(
                                f"[BUY_SELL_DAILY] Found complete price_daily data: date={end} "
                                f"with {price_coverage_symbols} symbols"
                            )
                            break

                # Fallback if no complete data found
                if end is None:
                    # Use most recent date with ANY price data
                    cur.execute(
                        "SELECT MAX(date) FROM price_daily WHERE date <= %s",
                        (now_et.date(),),
                    )
                    price_max_date_row = cur.fetchone()
                    if price_max_date_row is None or price_max_date_row[0] is None:
                        raise RuntimeError(
                            f"CRITICAL: No price_daily data found at all. "
                            "Cannot generate signals without price data."
                        )
                    end = price_max_date_row[0]

                    cur.execute(
                        "SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = %s",
                        (end,),
                    )
                    price_row = cur.fetchone()
                    if price_row and price_row[0]:
                        price_coverage_symbols = int(price_row[0])
                        logger.warning(
                            f"[BUY_SELL_DAILY] No complete price_daily data found. "
                            f"Using most recent: date={end} with {price_coverage_symbols} symbols "
                            f"(< 3000 minimum). Signals may be degraded."
                        )
                    else:
                        raise RuntimeError(
                            f"CRITICAL: price_daily coverage query failed for {end}. "
                            "Cannot generate signals without price data."
                        )

                if price_coverage_symbols == 0:
                    raise RuntimeError(
                        f"CRITICAL: No price data found for {end}. "
                        "Upstream loader failed. Cannot generate signals without price data."
                    )

                # Count symbols with tech data within 10 calendar days of end.
                # On days when TechnicalDataDaily loads partial coverage (e.g., new symbols added
                # mid-cycle, or price loader ran in two batches), some symbols have end-1d tech data
                # instead of exact end-date data. Those symbols still generate valid signals since
                # _fetch_signal_data queries t.date <= end (uses best available tech row).
                cur.execute(
                    """SELECT COUNT(DISTINCT symbol), MAX(date) FROM technical_data_daily
                       WHERE date >= %s AND date <= %s""",
                    (end - timedelta(days=10), end),
                )
                tech_row = cur.fetchone()
                if tech_row is None:
                    raise RuntimeError(
                        f"CRITICAL: technical_data_daily query returned None for {end}. "
                        "Query malformed or table empty. Cannot determine technical data availability."
                    )
                if len(tech_row) < 2:
                    raise RuntimeError(
                        f"CRITICAL: technical_data_daily query returned invalid structure. "
                        f"Expected 2 columns, got {len(tech_row)}."
                    )
                if tech_row[0] is None:
                    raise RuntimeError(
                        f"CRITICAL: technical_data_daily row count query returned NULL for {end}. "
                        "Database query or upstream loader may have failed."
                    )
                tech_coverage_symbols = int(tech_row[0])
                if tech_coverage_symbols == 0:
                    raise RuntimeError(
                        f"CRITICAL: No symbols found in technical_data_daily within 10 days of {end}. "
                        "Upstream loader failed. Cannot generate signals."
                    )
                tech_max_date = tech_row[1]

                # ISSUE #9 FIX: Pre-cache all per-symbol watermarks at startup
                # Fetch in one query: symbol -> max(date) mapping for entire table
                # Prevents 10k individual queries on ECS restart (would stall if any single query is slow)
                symbol_watermarks = {}
                cur.execute(
                    "SELECT symbol, MAX(date) FROM buy_sell_daily GROUP BY symbol",
                )
                for row in cur.fetchall():
                    symbol, max_date = row
                    if max_date:
                        symbol_watermarks[symbol] = max_date

            today_et = now_et.date()
            tech_data_age = (today_et - tech_max_date).days if tech_max_date else None

            self._batch_context = {
                "end_date": end,
                "price_coverage_symbols": price_coverage_symbols,
                "tech_coverage_symbols": tech_coverage_symbols,
                "tech_data_age": tech_data_age,
                "symbol_watermarks": symbol_watermarks,
            }
            logger.debug(
                f"Batch context: end={end}, price_coverage={price_coverage_symbols}, "
                f"tech_coverage={tech_coverage_symbols}, cached {len(symbol_watermarks)} symbol watermarks"
            )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"[BATCH_CONTEXT] Failed to prepare batch context for buy_sell_daily: {e}. "
                "Cannot proceed without shared batch data (end_date, price/tech coverage, symbol watermarks)."
            ) from e

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:  # noqa: C901
        """Generate signals from technical data."""
        # Validate batch context was properly initialized
        if not self._batch_context or "end_date" not in self._batch_context:
            raise RuntimeError(
                "[BUY_SELL_DAILY] Batch context not properly initialized. "
                "_prepare_batch_context() must be called before fetch_incremental(). "
                "This indicates run() was called but batch context setup failed or was skipped."
            )
        end = self._batch_context["end_date"]

        # ISSUE #9 FIX: Look up symbol watermark from pre-cached batch_context
        # (populated at startup with all symbols' watermarks in one query).
        # Database fallback only for newly added symbols not in pre-cached watermarks.
        # Prevents stalls on ECS restart when fetching per-symbol watermarks.
        if since is None:
            try:
                # CRITICAL: Validate symbol_watermarks exists in batch_context
                symbol_watermarks = self._batch_context.get("symbol_watermarks")
                if symbol_watermarks is None:
                    raise RuntimeError(
                        f"[WATERMARK] {symbol}: 'symbol_watermarks' missing from batch context. "
                        "_prepare_batch_context() must populate symbol_watermarks dict. "
                        "This indicates batch context initialization failed or was incomplete."
                    )

                max_date = None
                if not isinstance(symbol_watermarks, dict):
                    raise TypeError(
                        f"[WATERMARK] symbol_watermarks must be dict, got {type(symbol_watermarks).__name__}. "
                        "Batch context corrupted."
                    )

                # Lookup in pre-cached watermarks
                max_date = symbol_watermarks.get(symbol)
                if max_date is None:
                    # Cache miss: symbol not in pre-cached watermarks (likely newly added)
                    # Query database as legitimate fallback for new symbols
                    logger.debug(f"[WATERMARK] {symbol}: Not in cached watermarks - querying database for new symbol")
                    with DatabaseContext("read") as cur:
                        cur.execute(
                            "SELECT MAX(date) FROM buy_sell_daily WHERE symbol = %s",
                            (symbol,),
                        )
                        row = cur.fetchone()
                        if row is not None and len(row) >= 1 and row[0] is not None:
                            max_date = row[0]
                            logger.debug(f"[WATERMARK] {symbol}: Database query found max_date={max_date}")
                        else:
                            logger.debug(f"[WATERMARK] {symbol}: No watermark in database - first run for this symbol")

                # Convert max_date to date if found
                if max_date is not None:
                    if isinstance(max_date, date) and not isinstance(max_date, datetime):
                        since = max_date
                    elif isinstance(max_date, datetime):
                        since = max_date.date()
                    else:
                        raise RuntimeError(
                            f"[BUY_SELL_DAILY] {symbol}: Unexpected date type from watermark: {type(max_date).__name__}. "
                            f"Expected date or datetime, got: {max_date}. "
                            f"Database query may be returning wrong type or corrupted data."
                        )
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                raise RuntimeError(
                    f"[BUY_SELL_DAILY] Failed to read watermark for {symbol}: {e}. "
                    "Cannot determine incremental load point for buy/sell signal computation."
                ) from e

        if since is None:
            start = end - timedelta(days=30)
        else:
            # FIXED Issue #22: Use since - 1 day for watermark (standard across all loaders)
            # This ensures we get overlap data for cross-checking and prevents gaps
            start = since - timedelta(days=1)

        # ISSUE #7 FIX: Validate technical_data_daily COMPLETENESS, not just existence
        # Check that technical_data_daily has been loaded for ALL active symbols, not just this one
        # If loader completed but missed symbols, we'll generate signals only for covered symbols,
        # creating inconsistent signal coverage which breaks Phase 5 filtering
        try:
            with DatabaseContext("read") as cur:
                # Verify this symbol has recent technical data (within 10 days of end_date).
                # On partial-coverage days some symbols' latest tech date is end-1d because
                # TechnicalDataDaily ran before all prices were available. Accept any tech data
                # within the window — _fetch_signal_data queries t.date <= end so it will use
                # the most recent available row for signal computation.
                cur.execute(
                    """SELECT MAX(date) FROM technical_data_daily
                       WHERE symbol = %s AND date >= %s AND date <= %s""",
                    (symbol, end - timedelta(days=10), end),
                )
                row = cur.fetchone()
                if row is None or row[0] is None:
                    raise RuntimeError(
                        f"[BUY_SELL_DAILY] {symbol}: No technical data within 10 days of {end}. "
                        "Technical data is CRITICAL for buy/sell signal generation. "
                        "Indicates symbol was never processed by TechnicalDataDaily. Cannot proceed."
                    )

                # Validate upstream loader completeness before generating signals.
                # buy_sell_daily depends on price_daily and technical_data_daily.
                #
                # DENOMINATOR FIX: Use price_daily count as the denominator, NOT all active symbols.
                # Reason: active symbol count (10,000+) includes ETFs and newly listed symbols
                # without price history. Comparing against all active symbols gives misleadingly
                # low coverage even on successful load days (e.g., 73% when 80%+ loaded fine).
                #
                # THRESHOLD: 70% of price symbols must have technical data (normal days: ~80-83%).
                # This correctly identifies partial failures (e.g., 46% on June 5 = anomaly)
                # while allowing normal operations to proceed.

                # ROOT CAUSE #4 FIX: Use cached counts from batch context (computed once)
                # instead of querying per-symbol. Eliminates ~20k per-symbol database queries.
                if not self._batch_context:
                    raise RuntimeError(
                        f"{symbol}: batch context not initialized. "
                        "Cannot determine data coverage without batch context."
                    )
                if "price_coverage_symbols" not in self._batch_context:
                    raise RuntimeError(
                        f"{symbol}: batch context missing 'price_coverage_symbols'. "
                        "Coverage validation failed - cannot verify price data availability."
                    )
                if "tech_coverage_symbols" not in self._batch_context:
                    raise RuntimeError(
                        f"{symbol}: batch context missing 'tech_coverage_symbols'. "
                        "Coverage validation failed - cannot verify technical data availability."
                    )
                price_coverage_symbols = self._batch_context["price_coverage_symbols"]
                tech_coverage_symbols = self._batch_context["tech_coverage_symbols"]

                # Require minimum price coverage (warning only if less than optimal)
                if price_coverage_symbols < 1000:
                    raise RuntimeError(
                        f"{symbol}: price_daily insufficient for {end}: only "
                        f"{price_coverage_symbols} symbols (minimum 1000 required). "
                        "Cannot generate signals without minimum price data coverage."
                    )
                elif price_coverage_symbols < 3000:
                    logger.warning(
                        f"{symbol}: Generating signals with reduced price coverage "
                        f"({price_coverage_symbols} symbols, optimal >= 3000)"
                    )
                # Technical coverage relative to price coverage (normal: 80-83%)
                tech_coverage = (
                    (tech_coverage_symbols / price_coverage_symbols * 100) if price_coverage_symbols > 0 else 0
                )

                # CRITICAL: Signal generation requires COMPLETE technical data (95%+ coverage minimum).
                # Accepting 70-80% coverage means 20-30% of symbols lack complete technical patterns.
                # Signals generated without technical data are degraded:
                # - Missing moving averages (trend validation breaks)
                # - Missing momentum indicators (signal quality degrades)
                # - Missing volume patterns (entry confirmation fails)
                # Position sizing and exit logic depend on complete technical analysis.
                min_tech_coverage = 95.0
                if tech_coverage < min_tech_coverage:
                    raise RuntimeError(
                        f"{symbol}: technical_data_daily incomplete for {end}: "
                        f"Only {tech_coverage:.1f}% coverage (need >= {min_tech_coverage:.1f}%). "
                        f"{tech_coverage_symbols}/{price_coverage_symbols} price symbols have technical data. "
                        f"Cannot generate reliable signals with {100 - tech_coverage:.1f}% missing technical indicators. "
                        f"({tech_coverage:.1f}%, required >= 70%). "
                        "Cannot generate buy/sell signals without sufficient technical data coverage."
                    )
        except Exception as e:
            raise RuntimeError(
                f"[BUY_SELL_DAILY] Failed to validate data for {symbol}: {e}. "
                "Cannot generate signals without validation."
            ) from e

        # Fetch and generate signals - gracefully handle per-symbol failures by creating sentinel rows
        try:
            # Fetch required data for signal generation
            rows = self._fetch_signal_data(symbol, start, end)
            if not rows:
                logger.error(f"[BUY_SELL_DAILY] {symbol}: _fetch_signal_data returned no rows for {start} to {end}")
                return [
                    {
                        "symbol": symbol,
                        "date": end.isoformat(),
                        "data_unavailable": True,
                        "reason": "_fetch_signal_data returned no rows for signal date range",
                    }
                ]

            # Generate signals
            signals = self._generate_signals(symbol, rows)

            # Defensive: Handle case where _generate_signals returns None (should not happen, but add guard)
            if signals is None:
                logger.error(f"[BUY_SELL_DAILY] {symbol}: _generate_signals returned None instead of list")
                signals = [{
                    "symbol": symbol,
                    "date": end.isoformat(),
                    "data_unavailable": True,
                    "reason": "signal generation returned None (internal error)"
                }]
            elif not isinstance(signals, list):
                logger.error(f"[BUY_SELL_DAILY] {symbol}: _generate_signals returned {type(signals).__name__} instead of list")
                signals = [{
                    "symbol": symbol,
                    "date": end.isoformat(),
                    "data_unavailable": True,
                    "reason": f"signal generation returned {type(signals).__name__} instead of list"
                }]

            # Mark all successful signals with data_unavailable=False and reason=None
            for sig in signals:
                sig["data_unavailable"] = False
                sig["reason"] = None

            # Filter to incremental range if needed
            if since is not None:
                from utils.validation import safe_parse_date

                filtered_signals = []
                for s in signals:
                    signal_date = safe_parse_date(s["date"], "signal filtering")
                    if signal_date and signal_date > since:
                        filtered_signals.append(s)
                signals = filtered_signals

            return signals

        except Exception as e:
            # Per-symbol failure - create sentinel row instead of failing entire batch
            error_msg = str(e)
            # Truncate reason to 255 chars to fit VARCHAR(255) column
            reason = error_msg[:255] if len(error_msg) > 255 else error_msg
            logger.error(f"[BUY_SELL_DAILY] {symbol}: Signal generation failed: {error_msg}")
            return [{"symbol": symbol, "date": end.isoformat(), "data_unavailable": True, "reason": reason}]

    def get_tech_data_age(self) -> float | None:
        """Return current batch tech_data_age for signal generation.

        Facade elimination: public getter for _batch_context['tech_data_age']
        used by SignalsDailyLoaderFacade to eliminate private member access.

        Returns:
            Age in days (float), or None if batch context unavailable.
            Explicitly logs when batch context is missing (data unavailable).
        """
        if not self._batch_context:
            logger.debug(
                "[TECH_DATA_AGE] Batch context not initialized - tech data age unavailable. Signal generation may have incomplete optional data."
            )
            return None

        tech_data_age = self._batch_context.get("tech_data_age")
        if tech_data_age is None:
            logger.debug(
                "[TECH_DATA_AGE] 'tech_data_age' not in batch context - technical data freshness unavailable (optional enrichment)"
            )
        return tech_data_age

    def _fetch_signal_data(self, symbol: str, start: date, end: date) -> list[dict[str, Any]]:
        """Fetch technical and price data needed for signal generation."""
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """SELECT t.date, t.rsi, t.macd, t.macd_signal,
                              t.sma_50, t.sma_200, t.ema_12, t.ema_21, t.atr,
                              t.adx, t.mansfield_rs,
                              p.close, p.volume, p.open, p.high, p.low
                       FROM technical_data_daily t
                       LEFT JOIN price_daily p ON t.symbol = p.symbol AND t.date = p.date
                       WHERE t.symbol = %s AND t.date >= %s AND t.date <= %s
                       ORDER BY t.date ASC""",
                    (symbol, start, end),
                )
                rows = []
                dropped_rows = 0
                for r in cur.fetchall():
                    if r[0] is None or r[11] is None:
                        dropped_rows += 1
                        logger.debug(
                            f"{symbol} [{r[0]}]: Row dropped - missing required field (date={r[0]}, close={r[11]})"
                        )
                        continue
                    rows.append(
                        {
                            "date": r[0].isoformat() if r[0] is not None else None,
                            "rsi": float(r[1]) if r[1] is not None else None,
                            "macd": float(r[2]) if r[2] is not None else None,
                            "macd_signal": float(r[3]) if r[3] is not None else None,
                            "sma_50": float(r[4]) if r[4] is not None else None,
                            "sma_200": float(r[5]) if r[5] is not None else None,
                            "ema_12": float(r[6]) if r[6] is not None else None,
                            "ema_21": float(r[7]) if r[7] is not None else None,
                            "atr": float(r[8]) if r[8] is not None else None,
                            "adx": float(r[9]) if r[9] is not None else None,
                            "mansfield_rs": float(r[10]) if r[10] is not None else None,
                            "close": float(r[11]) if r[11] is not None else None,
                            "volume": int(r[12]) if r[12] is not None else None,
                            "open": float(r[13]) if r[13] is not None else None,
                            "high": float(r[14]) if r[14] is not None else None,
                            "low": float(r[15]) if r[15] is not None else None,
                        }
                    )
                if dropped_rows > 0:
                    raise RuntimeError(
                        f"[BUY_SELL] {symbol}: Dropped {dropped_rows} row(s) due to missing date or close price — "
                        "cannot generate signals with incomplete technical data; all dates and closes required"
                    )
                return rows
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(
                f"[BUY_SELL] Failed to fetch signal data for {symbol}: {e}. "
                "Cannot generate signals without complete technical data."
            ) from e

    def _generate_signals(self, symbol: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Generate buy/sell signals matching Pine Script pivot-breakout logic.

        BUY: High > recent_swing_high AND close > SMA50 (breakout above pivot with trend filter)
        SELL: Low < recent_swing_low (stop loss trigger)
        """
        handler = BuySignalGenerator()

        # Validate and retrieve tech_data_age with explicit logging
        if not self._batch_context:
            logger.warning(
                f"[SIGNAL_GEN] {symbol}: Batch context not initialized - "
                "tech data age unavailable for signal generation"
            )
            tech_data_age = None
        else:
            tech_data_age = self._batch_context.get("tech_data_age")
            if tech_data_age is None:
                logger.warning(
                    f"[SIGNAL_GEN] {symbol}: 'tech_data_age' missing from batch context - "
                    "cannot assess data freshness for signal generation"
                )

        return handler.run(symbol, rows, tech_data_age)

    # Columns with DECIMAL(8,4) precision - max 9999.9999
    # High-priced stocks (ASML, BLK, CAT, etc.) can produce values ≥10000 for
    # percentage/ratio fields, causing PostgreSQL numeric field overflow on COPY.
    _DECIMAL84_COLS = frozenset(
        {
            "signal_strength",
            "volume_surge_pct",
            "rsi",
            "adx",
            "pct_from_ema21",
            "pct_from_sma50",
            "mansfield_rs",
            "sata_score",
            "risk_reward_ratio",
            "risk_pct",
            "entry_quality_score",
            "signal_quality_score",
            "position_size_recommendation",
            "current_gain_pct",
            "stage_confidence",
            "strength",
        }
    )
    decimal84_max = 9999.9999

    def transform(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Cap DECIMAL(8,4) columns to prevent numeric field overflow on high-price stocks.

        Also ensures data_unavailable and reason columns are present on all rows.
        """
        for row in rows:
            # Ensure data_unavailable and reason columns are present on all rows
            if "data_unavailable" not in row:
                row["data_unavailable"] = False
            if "reason" not in row:
                row["reason"] = None

            # Skip metric validation and capping for sentinel rows (data_unavailable=True)
            if row.get("data_unavailable"):
                continue

            capped_cols = []
            for col in self._DECIMAL84_COLS:
                v = row.get(col)
                if v is not None and isinstance(v, (int, float)) and abs(v) > self.decimal84_max:
                    capped_cols.append(col)
                    row[col] = self.decimal84_max if v > 0 else -self.decimal84_max
            if capped_cols:
                row["_metrics_capped_at_db_limit"] = capped_cols
                logger.warning(
                    f"{row.get('symbol')} [{row.get('date')}]: Metrics capped at {self.decimal84_max}: {capped_cols}"
                )
        return rows


def main() -> int:  # noqa: C901
    """Load daily trading signals.

    Exit codes: 0=success, 1=error, 2=no_data
    """
    parser = argparse.ArgumentParser(description="Load daily trading signals")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols")
    parser.add_argument(
        "--parallelism",
        type=int,
        default=get_default_parallelism("buy_sell_daily"),
        help="Parallel workers",
    )
    args = parser.parse_args()

    try:
        if args.symbols:
            symbols = args.symbols.split(",")
        else:
            symbols = get_active_symbols(timeout_secs=300)
            if not symbols:
                logger.warning("[LOADER] No symbols found in stock_symbols table. Exit code 1 (ERROR).")
                return 1
    except Exception as e:
        logger.error(f"[LOADER] Failed to fetch active symbols: {e}. Exit code 1 (ERROR).")
        return 1

    logger.info(f"Starting buy_sell_daily loader with {len(symbols)} symbols, parallelism={args.parallelism}")

    # VALIDATION: buy_sell_daily is critical path; parallelism should be 3 per steering doc line 44-48
    # If parallelism > 4, log warning as it may cause RDS connection pool exhaustion
    if args.parallelism > 4:
        logger.warning(
            f"[PARALLELISM] buy_sell_daily: parallelism={args.parallelism} exceeds recommended max (3). "
            "This may cause RDS connection pool exhaustion. Check ECS task definition and LOADER_PARALLELISM env var."
        )

    # Check upstream loader status (ISSUE #28 FIX: dependency validation)
    try:
        with DatabaseContext("read") as cur:
            # Verify price_daily is not stuck RUNNING/PENDING
            cur.execute("SELECT status FROM data_loader_status WHERE table_name = 'price_daily'")
            result = cur.fetchone()
            if result is None:
                raise RuntimeError(
                    "CRITICAL: data_loader_status has no record for price_daily. "
                    "Loader tracking broken or upstream hasn't run. Cannot proceed."
                )
            if len(result) < 1:
                raise RuntimeError(
                    f"CRITICAL: data_loader_status query returned invalid row structure. "
                    f"Expected at least 1 column, got {len(result)}. Query may be malformed."
                )
            prices_status = result[0]
            if prices_status not in ("COMPLETED", "success", "OK"):
                logger.error(
                    f"[DEPENDENCY] Aborting buy_sell_daily: price_daily status is {prices_status}. "
                    f"Expected COMPLETED/success/OK. Cannot generate signals without complete price data."
                )
                return 1  # Return error code (1), will retry on next pipeline run
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as status_err:
        logger.error(
            f"[LOADER] Failed to check price_daily status: {status_err}. "
            "Cannot verify upstream loader is ready. Exit code 1 (ERROR)."
        )
        return 1

    # ISSUE #7: Validate dependency - technical_data_daily must be fresh and have good coverage
    try:
        with DatabaseContext("read") as cur:
            cur.execute("SELECT MAX(date) FROM technical_data_daily")
            result = cur.fetchone()
            if result is None or len(result) < 1 or result[0] is None:
                logger.error("[DEPENDENCY] technical_data_daily is empty - cannot generate signals")
                return 1

            tech_data_date = result[0]
            if not isinstance(tech_data_date, date):
                tech_data_date = date.fromisoformat(str(tech_data_date))
            # FIX: Use ET date, not system date (AWS runs in UTC but trading is ET-based)
            today_et = datetime.now(EASTERN_TZ).date()
            tech_data_age = (today_et - tech_data_date).days

            # Compare against last trading day, not calendar days.
            # On Monday, Friday's data is 2 calendar days old but 0 trading days stale.
            from algo.infrastructure import MarketCalendar

            last_trading_day = today_et
            for _ in range(10):
                if MarketCalendar.is_trading_day(last_trading_day):
                    break
                last_trading_day -= timedelta(days=1)
            # Allow data from the last 2 trading days (covers Monday with Friday data)
            prev_trading_day = last_trading_day - timedelta(days=1)
            for _ in range(7):
                if MarketCalendar.is_trading_day(prev_trading_day):
                    break
                prev_trading_day -= timedelta(days=1)

            if tech_data_date < prev_trading_day:
                logger.error(
                    f"[DEPENDENCY] technical_data_daily is {tech_data_age}+ days old (data: {tech_data_date}, "
                    f"last trading day: {last_trading_day}) - too stale for signal generation"
                )
                return 1

            if not symbols:
                logger.error(
                    "[DEPENDENCY] Symbol list is empty. Cannot calculate coverage percentage. Exit code 1 (ERROR)."
                )
                return 1

            cur.execute("""
                SELECT COUNT(DISTINCT symbol) FROM technical_data_daily
                WHERE date = (SELECT MAX(date) FROM technical_data_daily)
            """)
            cur_row = cur.fetchone()
            if cur_row is None or len(cur_row) < 1:
                logger.error(
                    "[DEPENDENCY] Failed to count technical_data_daily symbols. Invalid row structure. Exit code 1 (ERROR)."
                )
                return 1
            if cur_row[0] is None:
                logger.error("[DEPENDENCY] technical_data_daily symbol count is NULL. Exit code 1 (ERROR).")
                return 1
            tech_symbol_count = int(cur_row[0])
            if tech_symbol_count == 0:
                logger.error(
                    "[DEPENDENCY] No symbols found in technical_data_daily on latest date. Exit code 1 (ERROR)."
                )
                return 1

            coverage_pct = round(100 * tech_symbol_count / len(symbols), 1)
            if coverage_pct < 73:
                logger.error(
                    f"[DEPENDENCY] technical_data_daily coverage is {coverage_pct}% ({tech_symbol_count}/{len(symbols)} symbols) - below 73% threshold"
                )
                return 1

            logger.info(
                f"[DEPENDENCY] ✓ technical_data_daily: {tech_symbol_count}/{len(symbols)} symbols ({coverage_pct}%), age {tech_data_age}d"
            )
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as dep_err:
        logger.error(f"[LOADER] Failed to validate technical_data_daily dependency: {dep_err}. Exit code 1 (ERROR).")
        return 1

    loader = SignalsDailyLoader()
    try:
        result = loader.run(symbols, parallelism=args.parallelism)
        logger.info("[LOADER] Daily signals load completed successfully. Exit code 0 (SUCCESS).")

        # ISSUE #27 FIX: Make technical data enrichment part of the critical path.
        # Enrichment is optional - if the module doesn't exist, skip it but mark loader as COMPLETED.
        logger.info("[LOADER] Starting technical data enrichment (optional)...")
        try:
            from loaders.enrich_buy_sell_daily_technical import enrich_technical_data

            try:
                enrich_result = enrich_technical_data(
                    since=today_et - timedelta(days=3), symbols=None, min_success_rate=0.95
                )
                logger.info(
                    f"[LOADER] ✓ Technical enrichment complete: {enrich_result['updated']} updated, "
                    f"{enrich_result['checked']} checked, {enrich_result['nulls_remaining']} nulls remaining"
                )
            except RuntimeError as e:
                # Enrichment failed to meet quality threshold - log but don't fail
                logger.warning(f"[LOADER] Technical data enrichment failed: {e}. Continuing with load.")
        except ImportError as e:
            # Enrichment module not available - this is OK, it's optional
            logger.info(f"[LOADER] Technical data enrichment module not available ({e}). Skipping enrichment.")

        # CRITICAL FIX: Update loader status to COMPLETED with actual latest_date from table
        # Bug fix: Use MAX(date) from buy_sell_daily, not calendar date (today_et)
        # Root cause: Reporting today's calendar date when signals may only be generated through yesterday
        try:
            with DatabaseContext("write") as cur:
                cur.execute("SET statement_timeout = 0")
                # Get actual maximum date from buy_sell_daily (signals generated up to this date)
                cur.execute("SELECT COALESCE(MAX(date), %s) FROM buy_sell_daily", (today_et,))
                actual_max_date = cur.fetchone()[0]

                cur.execute(
                    """UPDATE data_loader_status
                       SET status = %s, latest_date = %s, last_updated = NOW(), completion_pct = 100.0
                       WHERE table_name = %s""",
                    ("COMPLETED", actual_max_date, "buy_sell_daily"),
                )
                logger.info(f"[STATUS] Updated buy_sell_daily status to COMPLETED with latest_date={actual_max_date} (actual table max, not calendar date)")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as status_err:
            logger.error(f"[STATUS] Could not update loader status to COMPLETED: {status_err}")
            return 1

        return 0
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"[LOADER] Daily signals load failed: {e}. Exit code 1 (ERROR).")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as e:
        logger.error(str(e))
        sys.exit(1)
