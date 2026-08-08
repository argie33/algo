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

from algo.infrastructure import MarketCalendar
from algo.signals.buy_signal_generator import BuySignalGenerator
from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ
from utils.loaders.config import get_default_parallelism
from utils.loaders.helpers import get_active_symbols
from utils.loaders.status_manager import LoaderStatusManager
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


def _check_signal_degradation(cur: Any, min_signals_per_day_threshold: int = 150) -> None:
    """Raise if buy_sell_daily shows unexpected signal degradation over 3-day rolling window.

    TWO-LEVEL CHECK:
    1. Absolute minimum: Latest day must have >= min_signals_per_day_threshold (catches sudden collapse)
    2. Relative degradation: Latest day < 50% of 3-day median (catches slow drift)

    HISTORY:
    - Previous all-time average check masked 9+ days of stale data (diluted by old healthy days)
    - Single-day check caught immediate failures but missed slow 3-day degradation
    - New median check catches both: sudden drops AND sustained drift over multiple days

    This prevents false positives from 1-2 bad days while catching real degradation patterns.
    """
    cur.execute("SELECT MAX(date) FROM buy_sell_daily")
    result = cur.fetchone()
    latest_signal_date = result[0] if result else None
    if latest_signal_date is None:
        return

    # Check absolute minimum on latest day
    cur.execute("SELECT COUNT(*) FROM buy_sell_daily WHERE date = %s", (latest_signal_date,))
    result = cur.fetchone()
    latest_day_signals = result[0] if result else 0

    if latest_day_signals < min_signals_per_day_threshold:
        raise RuntimeError(
            f"[SIGNAL_DEGRADATION_DETECTED] buy_sell_daily's most recent date "
            f"({latest_signal_date}) has only {latest_day_signals} signals "
            f"(expected >= {min_signals_per_day_threshold}). This indicates either: "
            f"(1) Pivot detection logic is too strict, (2) Price/technical data quality "
            f"is poor, (3) upstream price_daily/technical_data_daily coverage collapsed, "
            f"or (4) this run silently failed to advance the watermark. "
            f"Phase 7 requires minimum ~300 signals/day to function. "
            f"OPERATOR ACTION: Check BuySignalGenerator logic and price_daily coverage. "
            f"Do NOT accept this as normal - investigate immediately."
        )

    # CRITICAL: Also check 3-day rolling median to catch slow degradation
    # A single bad day might be legitimate (holiday, market event), but 3-day drift indicates
    # upstream loader failure (technical_data_daily partial failure, etc.)
    cur.execute("""
        WITH recent_days AS (
            SELECT date, COUNT(*) as signal_count
            FROM buy_sell_daily
            WHERE date > %s - INTERVAL '10 days'
            GROUP BY date
            ORDER BY date DESC
            LIMIT 3
        )
        SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY signal_count) as median_signals
        FROM recent_days
    """, (latest_signal_date,))

    result = cur.fetchone()
    if result and result[0] is not None:
        median_3day = float(result[0])
        degradation_threshold = median_3day * 0.5  # Flag if latest < 50% of 3-day median

        if latest_day_signals < degradation_threshold:
            raise RuntimeError(
                f"[SIGNAL_DEGRADATION_DETECTED] buy_sell_daily showing sustained degradation. "
                f"Latest day ({latest_signal_date}): {latest_day_signals} signals. "
                f"3-day rolling median: {median_3day:.0f} signals. "
                f"Threshold: {degradation_threshold:.0f} (50% of median). "
                f"This indicates sustained upstream loader failure (not a single-day anomaly). "
                f"OPERATOR ACTION: Check technical_data_daily and price_daily loaders for partial failures. "
                f"Do NOT accept degraded signal generation - investigate immediately."
            )


class SignalsDailyLoader(OptimalLoader):
    """Daily signals loader that generates buy/sell signals from technical indicators."""

    table_name = "buy_sell_daily"
    primary_key = ("symbol", "date")
    watermark_field = "date"
    exclude_etfs_from_symbols = True  # Trading signals for stocks only, not ETFs

    def run(self, symbols: list[str], parallelism: int | None = None, backfill_days: int | None = None) -> dict[str, Any]:  # type: ignore[override]
        """Override run() to filter symbols to only those with stock_scores AND price_daily.

        CRITICAL FIX (Session 248): buy_sell_daily was generating signals for all active symbols (~10k),
        but stock_scores only covers ~4.7k symbols (quality/growth require SEC filings).
        This caused 99.5% of signals to be filtered out in Phase 7.
        Solution: Only generate signals for symbols with stock_scores available.

        CRITICAL FIX (Session 250): Additional filter for symbols with price_daily data on target date.
        Some stock_scores symbols don't have price_daily data (e.g., delisted, halted).
        This caused foreign key constraint violations when inserting signals.
        Solution: Intersect stock_scores universe with symbols that have actual price data.

        CRITICAL FIX (Session 357): Signals were stale because OptimalLoader watermark prevented
        re-processing dates already in buy_sell_daily. Solution: Delete signals for current trading
        date BEFORE regeneration to force watermark reset.
        """
        try:
            logger.info(f"[RUN] Starting with {len(symbols)} symbols")

            # Session 357 fix: Delete signals for today to force regeneration
            now_et = datetime.now(EASTERN_TZ)
            current_date = now_et.date()
            with DatabaseContext("write") as cur:
                cur.execute("DELETE FROM buy_sell_daily WHERE date = %s", (current_date,))
                deleted_count = cur.rowcount
                if deleted_count > 0:
                    logger.info(
                        f"[SESSION 357 FIX] Deleted {deleted_count} stale signals for {current_date} to force regeneration"
                    )

            # Only filter if symbols came from get_active_symbols() (not from explicit --symbols arg)
            # If user specified symbols explicitly, respect their choice
            if symbols and len(symbols) > 4000:  # Heuristic: if >4000 symbols, likely from get_active_symbols()
                logger.info("[RUN] Len > 4000, applying universe filter")
                with DatabaseContext("read") as cur:
                    cur.execute("SELECT symbol FROM stock_scores WHERE data_unavailable = false")
                    scored_symbols = {row[0] for row in cur.fetchall()}

                original_count = len(symbols)
                symbols = [s for s in symbols if s in scored_symbols]
                pct_retained = (len(symbols) / original_count * 100) if original_count > 0 else 0.0
                logger.info(
                    f"[UNIVERSE FILTER] Filtered buy_sell_daily symbols to stock_scores universe: "
                    f"{original_count} → {len(symbols)} symbols ({pct_retained:.1f}% retained)"
                )

                # DATA DELETION REMOVED (Session 262 Fix)
                # ISSUE: Pre-emptive deletion of signals for unscored symbols was too aggressive
                # When the loader failed to generate new signals (e.g., weekend with no market),
                # the pre-deleted data was gone forever, leaving empty tables.
                #
                # NEW APPROACH: Don't delete pre-emptively. Instead:
                # - Signal universe will naturally include only scored symbols (INNER JOIN in Phase 7)
                # - Unscored symbols' signals will simply not be used by downstream phases
                # - Historical data is preserved for analysis
                #
                # This follows fail-safe principle: keep data until explicitly proven unnecessary

            # CRITICAL FIX (Session 262): Filter to symbols with price_daily data on the TARGET DATE.
            # This runs ALWAYS, not just when len(symbols) > 4000.
            # Root cause: Loader was generating signals for symbols without price data, causing
            # foreign key constraint violations when trying to insert into buy_sell_daily.
            # Fix: BEFORE starting parallel generation, filter symbols to those with actual
            # price data on the target date. This prevents foreign key failures.
            if symbols:
                logger.info(f"[PRICE_FILTER] Starting price_daily filter for {len(symbols)} symbols")
                now_et = datetime.now(EASTERN_TZ)
                target_date = now_et.date()
                max_iterations = 10
                iterations = 0
                while (
                    target_date > date(2020, 1, 1)
                    and not MarketCalendar.is_trading_day(target_date)
                    and iterations < max_iterations
                ):
                    target_date = target_date - timedelta(days=1)
                    iterations += 1

                # Find the most recent date with good price_daily coverage
                with DatabaseContext("read") as cur:
                    # Query: Find most recent date with >= 90% coverage of our scored symbols
                    cur.execute(
                        """WITH recent_price_dates AS (
                           SELECT date, COUNT(DISTINCT symbol) as symbol_count
                           FROM price_daily
                           WHERE date <= %s
                           GROUP BY date
                           ORDER BY date DESC
                           LIMIT 7
                        )
                        SELECT date, symbol_count FROM recent_price_dates
                        WHERE symbol_count >= %s
                        ORDER BY date DESC
                        LIMIT 1""",
                        (target_date, max(1, int(len(symbols) * 0.90))),  # CRITICAL: >= 1 even if symbols empty
                    )

                    # CRITICAL FIX Session 345: Validate symbols list before using in calculations
                    if not symbols or len(symbols) == 0:
                        logger.warning(
                            "[LOAD_BUY_SELL_DAILY] Symbols list is empty. "
                            "Upstream filter (stock_scores or market regime) may have failed. "
                            "Using threshold of 1 instead of 0 to avoid matching all historical dates."
                        )
                    date_result = cur.fetchone()
                    if date_result:
                        price_data_date = date_result[0]
                        price_data_count = date_result[1]
                    else:
                        # Fallback: use most recent date regardless of coverage, BUT prefer current date if it has any price data
                        cur.execute("SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = %s", (target_date,))
                        current_date_row = cur.fetchone()
                        current_date_count = current_date_row[0] if current_date_row else 0

                        if current_date_count >= max(1, int(len(symbols) * 0.80)):
                            # Current date has acceptable coverage (80%+) - use it even if not the highest
                            price_data_date = target_date
                            price_data_count = current_date_count
                            logger.info(
                                f"[PRICE_FILTER] Using current date {target_date} with {current_date_count} symbols (80%+ threshold met)"
                            )
                        else:
                            # CRITICAL FIX: No fallback to degraded data - must meet minimum quality threshold
                            # Finance app requirement: never silently accept incomplete universe coverage
                            # If 90%+ threshold cannot be met, fail-fast to halt signal generation
                            raise RuntimeError(
                                f"[PRICE_FILTER CRITICAL] No price_daily data found with 90%+ coverage on or before {target_date}. "
                                f"Signal generation requires complete universe data (>=4500 of ~5000 symbols). "
                                f"Falling back to stale or incomplete data would violate fail-fast principle. "
                                f"ACTION: Check price_daily loader status, verify morning pipeline completed successfully."
                            )

                    # Get symbols that have price data on this date
                    cur.execute("""SELECT DISTINCT symbol FROM price_daily WHERE date = %s""", (price_data_date,))
                    price_symbols = {row[0] for row in cur.fetchall()}

                symbols_before_price_filter = len(symbols)
                symbols = [s for s in symbols if s in price_symbols]
                pct_retained_price = (len(symbols) / symbols_before_price_filter * 100) if symbols_before_price_filter > 0 else 0.0
                logger.info(
                    f"[PRICE_FILTER] Filtered to symbols with price_daily data on {price_data_date}: "
                    f"{symbols_before_price_filter} → {len(symbols)} symbols "
                    f"({pct_retained_price:.1f}% retained, price_data has {price_data_count} total)"
                )

                if not symbols:
                    raise RuntimeError(
                        f"CRITICAL: No symbols have price_daily data on {price_data_date}. "
                        "Cannot generate signals without prices. Check price loader status."
                    )
        except Exception as e:
            # CRITICAL FIX (Session 281): Price filtering is NON-NEGOTIABLE
            # If we proceed without valid prices, we create signals that violate foreign key constraints
            # Resulting signals cannot be inserted, causing data inconsistency and missing signals
            # Fail-closed: if price filtering fails, halt and wait for next data cycle
            logger.critical(
                f"[RUN] Price filter failed (critical for data integrity): {e}. "
                f"Cannot proceed without validating signals have corresponding price_daily data. "
                f"This prevents foreign key constraint violations. Data will be marked as unavailable."
            )
            raise RuntimeError(
                f"Price validation failed and is mandatory: {e}. "
                f"Cannot generate buy_sell signals without price_daily reference data."
            ) from e

        # Call parent run() with filtered symbols
        effective_parallelism: int = parallelism if parallelism is not None else 1
        result = super().run(symbols, parallelism=effective_parallelism, backfill_days=backfill_days)

        # FAIL-FAST: Validate that signal generation actually produced results
        # In a finance app, silent success with zero data is a critical failure
        rows_inserted = result.get("rows_inserted", 0)
        if rows_inserted == 0:
            # Check if this is due to upstream data being empty (legitimate) vs. a generation failure
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT COUNT(DISTINCT symbol) FROM buy_sell_daily WHERE date = (SELECT MAX(date) FROM buy_sell_daily)"
                )
                row = cur.fetchone()
                latest_count = row[0] if row and row[0] is not None else 0
                if latest_count == 0:
                    raise RuntimeError(
                        "[LOAD_BUY_SELL_DAILY] Generated ZERO signals for today. "
                        "Check: (1) technical_data_daily loaded for today, (2) stock_scores has coverage, "
                        "(3) price_daily has data for target date. This is a data loading failure."
                    )

        return result

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
                complete_date: date | None = None
                price_coverage_symbols = 0
                if complete_date_rows:
                    for row in complete_date_rows:
                        if row[1] >= 3000:
                            complete_date = row[0]
                            end = complete_date
                            price_coverage_symbols = int(row[1])
                            logger.info(
                                f"[BUY_SELL_DAILY] Found complete price_daily data: date={complete_date} "
                                f"with {price_coverage_symbols} symbols"
                            )
                            break

                # CRITICAL: No fallback to degraded data
                if complete_date is None:
                    # Must enforce strict minimum coverage threshold
                    # CRITICAL: Cannot generate signals with incomplete universe coverage
                    # Using prices older than yesterday for today's signals is unacceptable for trading
                    cur.execute(
                        "SELECT MAX(date) FROM price_daily WHERE date <= %s",
                        (now_et.date(),),
                    )
                    price_max_date_row = cur.fetchone()
                    if price_max_date_row is None or price_max_date_row[0] is None:
                        raise RuntimeError(
                            "CRITICAL: No price_daily data found at all. Cannot generate signals without price data."
                        )
                    complete_date = price_max_date_row[0]

                    # CRITICAL: Enforce max staleness - if price data is > 1 trading day old, FAIL
                    from algo.infrastructure import MarketCalendar
                    days_since_price = 0
                    check_date = end
                    while check_date > complete_date and check_date > date(2020, 1, 1):
                        if MarketCalendar.is_trading_day(check_date):
                            days_since_price += 1
                        if days_since_price > 1:
                            raise RuntimeError(
                                f"CRITICAL DATA QUALITY: Price data is {days_since_price} trading days old "
                                f"(latest: {complete_date}, target: {end}). "
                                f"This indicates upstream price loader failure or missing data. "
                                f"Cannot generate signals on multi-day-old prices - this violates trading safety requirements. "
                                f"Fail-fast: wait for price loader to complete."
                            )
                        check_date = check_date - timedelta(days=1)

                    end = complete_date

                    cur.execute(
                        "SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = %s",
                        (end,),
                    )
                    price_row = cur.fetchone()
                    if price_row and price_row[0]:
                        price_coverage_symbols = int(price_row[0])
                        # CRITICAL FIX (Session 416 + Session 442): STRICT 95% coverage requirement - NO FALLBACK
                        # Per GOVERNANCE.md: "Return None when price history missing or incomplete"
                        # Finance app requirement: Do not silently degrade universe coverage.
                        # Previous Sessions 248, 250: Fallback to degraded data caused 99.5% signal filtering in Phase 7.
                        # Solution: FAIL-FAST if coverage < 95% (allows only ~250 symbols degradation from full ~5000).
                        # This is non-negotiable: incomplete signals feed into portfolio decision-making.
                        min_coverage_threshold = 4750  # 95% of ~5000 symbol universe (strict, no fallback)
                        if price_coverage_symbols < min_coverage_threshold:
                            raise RuntimeError(
                                f"[BUY_SELL_DAILY FAIL-FAST] Insufficient price_daily coverage for signal generation. "
                                f"Got {price_coverage_symbols} symbols with prices on {end}. "
                                f"Required minimum: {min_coverage_threshold} symbols (95% of universe). "
                                f"Coverage: {price_coverage_symbols / min_coverage_threshold * 100:.1f}%. "
                                f"ROOT CAUSE: Upstream price_daily loader incomplete or failed. "
                                f"GOVERNANCE: Cannot generate signals with degraded universe coverage. "
                                f"ACTION: Wait for price_daily loader to complete. Check morning pipeline logs."
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

                # OPTIMIZATION (Session 262): Removed pre-caching of symbol watermarks.
                # Watermarks are no longer used for buy_sell_daily (see fetch_incremental comment).
                # This saves one TABLE SCAN on buy_sell_daily per run (minor optimization).
                symbol_watermarks: dict[str, date] = {}

                # N+1 FIX: per-symbol technical_data_daily freshness used to be a separate
                # MAX(date) query inside fetch_incremental for every symbol (~10k round
                # trips per run). One GROUP BY here replaces all of them.
                symbol_tech_max_dates = {}
                cur.execute(
                    """SELECT symbol, MAX(date) FROM technical_data_daily
                       WHERE date >= %s AND date <= %s GROUP BY symbol""",
                    (end - timedelta(days=10), end),
                )
                for row in cur.fetchall():
                    symbol, tech_max = row
                    if tech_max:
                        symbol_tech_max_dates[symbol] = tech_max

            today_et = now_et.date()
            tech_data_age = (today_et - tech_max_date).days if tech_max_date else None

            self._batch_context = {
                "end_date": end,
                "price_coverage_symbols": price_coverage_symbols,
                "tech_coverage_symbols": tech_coverage_symbols,
                "tech_data_age": tech_data_age,
                "symbol_watermarks": symbol_watermarks,
                "symbol_tech_max_dates": symbol_tech_max_dates,
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

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        # CRITICAL FIX (Session 262): buy_sell_daily generates signals for HISTORICAL dates,
        # not just incremental new dates. Therefore date-based watermarking doesn't work:
        # - Day 1: Generate signals for dates 2026-06-12 through 2026-07-17 → watermark=2026-07-17
        # - Day 2: Generate signals for same dates (technical indicators updated) → all filtered because date <= 2026-07-17
        #
        # Solution: IGNORE the watermark for buy_sell_daily. Generate all signals from lookback window
        # every run. Phase 7 (entry execution) will deduplicate via INNER JOIN to entry_records.
        # This ensures latest signals are always available even if technical indicators change.

        # Validate batch context was properly initialized
        if not self._batch_context or "end_date" not in self._batch_context:
            raise RuntimeError(
                "[BUY_SELL_DAILY] Batch context not properly initialized. "
                "_prepare_batch_context() must be called before fetch_incremental(). "
                "This indicates run() was called but batch context setup failed or was skipped."
            )
        end = self._batch_context["end_date"]

        # CRITICAL FIX (Session 262): Skip watermark lookup entirely for buy_sell_daily.
        # See comment above - we don't use watermarks for incremental loading because
        # signals are generated for historical dates, not just new dates. `since` is used
        # as passed in by the caller (see LOOKBACK FIX below for how a None/stale value
        # is handled).

        # LOOKBACK FIX (Session 263 EXTENDED): swing-pivot detection scans up to 50 bars back (~70+ calendar
        # days). Incremental runs must always have a full lookback window for pattern detection.
        # CRITICAL: If since is None, load full 120-day lookback. If since is close to end_date
        # (e.g., from load_symbol watermark reset), DON'T truncate - still use full lookback.
        # This prevents "no signals generated" on first run of a symbol.
        lookback_start = end - timedelta(days=120)
        if since is None:
            # First run (no watermark) - load full lookback from 120 days ago
            start = lookback_start
            logger.info(
                f"[BUY_SELL_DAILY] {symbol}: since=None (no watermark), loading full lookback " f"from {start} to {end}"
            )
        elif since >= end:
            # Watermark is at or after end_date (shouldn't happen after load_symbol reset, but guard it)
            # Reset to full lookback to ensure we have context
            logger.warning(
                f"[BUY_SELL_DAILY] {symbol}: since={since} is at/after end_date={end}. "
                f"Resetting to full lookback from {lookback_start} to {end}"
            )
            start = lookback_start
        else:
            # Normal incremental: use since - 1d for overlap, but floor at lookback_start
            # This ensures we always have enough historical context for swing detection
            start = min(since - timedelta(days=1), lookback_start)
            if start == lookback_start:
                logger.debug(
                    f"[BUY_SELL_DAILY] {symbol}: since={since} but using full lookback "
                    f"(since - 1d would be older than 120-day window)"
                )

        # ISSUE #7 FIX: Validate technical_data_daily COMPLETENESS, not just existence
        # Check that technical_data_daily has been loaded for ALL active symbols, not just this one
        # If loader completed but missed symbols, we'll generate signals only for covered symbols,
        # creating inconsistent signal coverage which breaks Phase 5 filtering
        try:
            # Verify this symbol has recent technical data (within 10 days of end_date).
            # On partial-coverage days some symbols' latest tech date is end-1d because
            # TechnicalDataDaily ran before all prices were available. Accept any tech data
            # within the window - _fetch_signal_data queries t.date <= end so it will use
            # the most recent available row for signal computation.
            # N+1 FIX: looked up from the batch-context GROUP BY cache instead of a
            # per-symbol MAX(date) query (~10k round trips per run eliminated).
            symbol_tech_max_dates = self._batch_context.get("symbol_tech_max_dates")
            if symbol_tech_max_dates is None:
                raise RuntimeError(
                    f"[BUY_SELL_DAILY] {symbol}: 'symbol_tech_max_dates' missing from batch context. "
                    "_prepare_batch_context() must populate it before fetch_incremental()."
                )
            if symbol_tech_max_dates.get(symbol) is None:
                # SENTINEL, NOT CRASH (2026-07-14): ~2,900 of 10,705 active symbols are
                # new/inactive listings with no price history and therefore no technical
                # data - a structural per-symbol gap, not a loader failure. Raising here
                # marked each of them failed and tripped the parallel 5% fail-rate gate,
                # killing the entire signals run (confirmed live). Emit the same explicit
                # data_unavailable marker this loader already uses for fetch/generation
                # errors; SYSTEMIC technical-data failures are still caught by the 95%
                # coverage gate below.
                logger.debug(
                    f"[BUY_SELL_DAILY] {symbol}: No technical data within 10 days of {end} - "
                    "marking data_unavailable (new/inactive listing without price history)"
                )
                return [
                    {
                        "symbol": symbol,
                        "date": end.isoformat(),
                        "data_unavailable": True,
                        "reason": f"no_technical_data_within_10d_of_{end}",
                        "reason_type": "not_applicable",
                    }
                ]

            # Validate upstream loader completeness before generating signals.
            # buy_sell_daily depends on price_daily and technical_data_daily.
            #
            # DENOMINATOR FIX: Use price_daily count as the denominator, NOT all active symbols.
            # Reason: active symbol count (10,000+) includes ETFs and newly listed symbols
            # without price history. Comparing against all active symbols gives misleadingly
            # low coverage even on successful load days (e.g., 73% when 80%+ loaded fine).
            #
            # ROOT CAUSE #4 FIX: Use cached counts from batch context (computed once)
            # instead of querying per-symbol. Eliminates ~20k per-symbol database queries.
            if not self._batch_context:
                raise RuntimeError(
                    f"{symbol}: batch context not initialized. Cannot determine data coverage without batch context."
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
            tech_coverage = (tech_coverage_symbols / price_coverage_symbols * 100) if price_coverage_symbols > 0 else 0

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
                        "reason_type": "loader_failed",
                    }
                ]

            # Generate signals
            signals = self._generate_signals(symbol, rows)

            # Defensive: Handle case where _generate_signals returns None (should not happen, but add guard)
            if signals is None:
                logger.error(f"[BUY_SELL_DAILY] {symbol}: _generate_signals returned None instead of list")
                signals = [
                    {
                        "symbol": symbol,
                        "date": end.isoformat(),
                        "data_unavailable": True,
                        "reason": "signal generation returned None (internal error)",
                        "reason_type": "loader_failed",
                    }
                ]
            elif not isinstance(signals, list):
                logger.error(
                    f"[BUY_SELL_DAILY] {symbol}: _generate_signals returned {type(signals).__name__} instead of list"
                )
                signals = [
                    {
                        "symbol": symbol,
                        "date": end.isoformat(),
                        "data_unavailable": True,
                        "reason": f"signal generation returned {type(signals).__name__} instead of list",
                        "reason_type": "loader_failed",
                    }
                ]

            # Mark only successful signals with data_unavailable=False
            # Preserve the reason from BuySignalGenerator (explains WHY signal was triggered)
            # (skip if signal already has data_unavailable=True from error handling above)
            for sig in signals:
                if not sig.get("data_unavailable", False):
                    sig["data_unavailable"] = False
                    # Keep reason from BuySignalGenerator - it contains signal reasoning
                    # (e.g., "Swing high breakout", "Support bounce", etc.)

            # CRITICAL FIX (Session 262): Do NOT filter signals by watermark for buy_sell_daily.
            # buy_sell_daily generates signals for historical dates (e.g., 120+ day lookback),
            # not just incremental dates. With watermark filtering, signals from dates <= watermark_date
            # are silently dropped on subsequent runs, even if technical indicators have been updated.
            #
            # Instead: Generate all signals from the full lookback window every run.
            # Downstream deduplication (Phase 7) handles avoiding duplicate entries via INNER JOIN to entry_records.
            #
            # This is safe because:
            # - Entry execution (Phase 8) will not re-execute a symbol that already has an entry_record
            # - Phase 7 deduplication ensures each signal only triggers one entry attempt
            # - Regenerating signals with updated technicals improves accuracy
            #
            # Removed: watermark filtering (if since is not None: filter signals)

            return signals

        except Exception as e:
            # Per-symbol failure - create sentinel row instead of failing entire batch
            error_msg = str(e)
            # Truncate reason to 255 chars to fit VARCHAR(255) column
            reason = error_msg[:255] if len(error_msg) > 255 else error_msg
            logger.error(f"[BUY_SELL_DAILY] {symbol}: Signal generation failed: {error_msg}")
            return [
                {
                    "symbol": symbol,
                    "date": end.isoformat(),
                    "data_unavailable": True,
                    "reason": reason,
                    "reason_type": "loader_failed",
                }
            ]

    def get_tech_data_age(self) -> float | None:
        """Return current batch tech_data_age for signal generation.

        Facade elimination: public getter for _batch_context['tech_data_age']
        used by SignalsDailyLoaderFacade to eliminate private member access.

        Returns:
            Age in days (float), or None if batch context unavailable.
            Explicitly logs when batch context is missing (data unavailable).
        """
        if not self._batch_context:
            logger.warning(
                "[TECH_DATA_AGE] Batch context not initialized - tech data age unavailable. Signal generation may have incomplete optional data."
            )
            return None

        tech_data_age = self._batch_context.get("tech_data_age")
        if tech_data_age is None:
            logger.warning(
                "[TECH_DATA_AGE] 'tech_data_age' not in batch context - technical data freshness unavailable (optional enrichment)"
            )
        return tech_data_age

    def _fetch_signal_data(self, symbol: str, start: date, end: date) -> list[dict[str, Any]]:
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """SELECT t.date, t.rsi, t.macd, t.macd_signal,
                              t.sma_50, t.sma_200, t.ema_12, t.ema_21, t.atr,
                              t.adx, t.mansfield_rs,
                              p.close, p.volume, p.open, p.high, p.low
                       FROM technical_data_daily t
                       INNER JOIN price_daily p ON t.symbol = p.symbol AND t.date = p.date
                       WHERE t.symbol = %s AND t.date >= %s AND t.date <= %s
                       ORDER BY t.date ASC""",
                    (symbol, start, end),
                )
                rows = []
                for r in cur.fetchall():
                    if len(r) < 16:
                        raise RuntimeError(
                            f"[BUY_SELL] {symbol}: Query returned {len(r)} columns, expected 16. "
                            f"Database schema mismatch or corrupted query result."
                        )
                    if r[0] is None or r[11] is None:
                        raise RuntimeError(
                            f"{symbol} [{r[0]}]: Query returned NULL date or close price - "
                            f"INNER JOIN should have excluded rows with missing price_daily. "
                            f"Database query may be corrupted or price_daily missing data."
                        )
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
        CRITICAL FIX: Filter out sentinel rows (data_unavailable=True) before returning.
        These rows indicate "no data available for this symbol" and should NOT be inserted
        into the database. They were previously being inserted with signal=NULL,
        causing Phase 7 to falsely detect stale data (Session 261).
        """
        input_count = len(rows)
        valid_rows = []
        sentinel_count = 0
        for row in rows:
            # Ensure data_unavailable and reason columns are present on all rows
            if "data_unavailable" not in row:
                row["data_unavailable"] = False
            if "reason" not in row:
                row["reason"] = None

            # CRITICAL: Sentinel rows (data_unavailable=True) indicate "skip this symbol"
            # They must NOT be inserted into buy_sell_daily table
            if row.get("data_unavailable"):
                sentinel_count += 1
                continue

            valid_rows.append(row)

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
        if input_count > 0:
            logger.info(f"[TRANSFORM] Processed {input_count} rows: {len(valid_rows)} valid, {sentinel_count} sentinel")
        return valid_rows


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
            # exclude_etfs=True matches this class's exclude_etfs_from_symbols=True (consumed
            # by loaders/runner.py's invocation path via getattr) - main() is the actual
            # production entrypoint (invoked directly by terraform/modules/loaders/main.tf) and
            # was previously bypassing this flag entirely, working only "by accident" because
            # the stock_scores intersection below happens to exclude ETFs too (they lack SEC
            # filings). Apply it explicitly here so both entrypoints agree by design, not luck.
            symbols = get_active_symbols(timeout_secs=300, exclude_etfs=True)
            if not symbols:
                logger.warning("[LOADER] No symbols found in stock_symbols table. Exit code 1 (ERROR).")
                return 1

            # CRITICAL FIX: Filter to only symbols with stock_scores (Session 248)
            # buy_sell_daily was generating signals for all active symbols (~10k),
            # but stock_scores only covers ~4.7k symbols (quality/growth require SEC filings).
            # This caused 99.5% of signals to be filtered out in Phase 7.
            # Solution: Only generate signals for symbols with stock_scores available.
            # Note: This reduces signal volume but ensures all signals can be ranked by Phase 7.
            #
            # GOVERNANCE: Universe filter is NON-NEGOTIABLE. Fail-fast if it fails.
            # Proceeding with all symbols when filter fails violates GOVERNANCE principle:
            # "Fail-fast on missing data. No silent fallbacks."
            with DatabaseContext("read") as cur:
                cur.execute("SELECT symbol FROM stock_scores WHERE data_unavailable = false")
                scored_symbols = {row[0] for row in cur.fetchall()}

            if not scored_symbols:
                raise RuntimeError(
                    "[UNIVERSE FILTER] CRITICAL: stock_scores table is empty or all marked unavailable. "
                    "Cannot generate signals without score-qualified symbols. "
                    "Check: (1) stock_scores loader completed, (2) data_unavailable flags correct."
                )

            original_count = len(symbols)
            symbols = [s for s in symbols if s in scored_symbols]
            logger.info(
                f"[UNIVERSE FILTER] Filtered buy_sell_daily symbols to only those with stock_scores: "
                f"{original_count} → {len(symbols)} symbols (removed {original_count - len(symbols)} without scores)"
            )

            if not symbols:
                raise RuntimeError(
                    "[UNIVERSE FILTER] CRITICAL: No symbols remain after filtering to stock_scores universe. "
                    "This means active_symbols have no corresponding stock_scores. "
                    "Check: (1) stock_scores loader covers all active symbols, (2) data_unavailable flags."
                )
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
            cur.execute("SELECT status, completion_pct FROM data_loader_status WHERE table_name = 'price_daily'")
            result = cur.fetchone()
            if result is None:
                raise RuntimeError(
                    "CRITICAL: data_loader_status has no record for price_daily. "
                    "Loader tracking broken or upstream hasn't run. Cannot proceed."
                )
            if len(result) < 2:
                raise RuntimeError(
                    f"CRITICAL: data_loader_status query returned invalid row structure. "
                    f"Expected 2 columns, got {len(result)}. Query may be malformed."
                )
            prices_status, prices_completion_pct = result
            # data_loader_status.status is written by two independent subsystems with
            # different vocabularies: the loader's own execution result (COMPLETED/ok, see
            # utils/loaders/status_enum.py) and algo/monitoring/pipeline_health.py's periodic
            # freshness sweep (HEALTHY/STALE/VERY_STALE/MISSING), which overwrites this same
            # column on every sweep. A status-string whitelist is racy - it blocks this loader
            # whenever the freshness sweep's value (price_daily sits at "HEALTHY" far more often
            # than "COMPLETED" in practice) is the most recent write. completion_pct is written
            # only by the loader itself and is a reliable execution signal - see
            # phase1_failsafe_retry.py for the same completion_pct-primary pattern.
            prices_ready = (prices_completion_pct is not None and prices_completion_pct >= 95.0) or prices_status in (
                "COMPLETED",
                "success",
                "OK",
                "ok",
                "HEALTHY",
            )
            if not prices_ready:
                logger.error(
                    f"[DEPENDENCY] Aborting buy_sell_daily: price_daily status is {prices_status}, "
                    f"completion_pct is {prices_completion_pct}. "
                    f"Cannot generate signals without complete price data."
                )
                return 1  # Return error code (1), will retry on next pipeline run
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as status_err:
        logger.error(
            f"[LOADER] Failed to check price_daily status: {status_err}. "
            "Cannot verify upstream loader is ready. Exit code 1 (ERROR)."
        )
        return 1

    # ISSUE #7: Validate dependency - technical_data_daily must be fresh and have good coverage
    # FIX: Define today_et outside try block so it's available for enrichment module (line 1119)
    today_et = datetime.now(EASTERN_TZ).date()
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

            # DENOMINATOR FIX (same as the one documented in fetch_incremental, which this
            # main()-level gate never received): the active-symbol list (10,000+) includes
            # ETFs and listings with no price history, so dividing by it reads misleadingly
            # low - 7,777 tech symbols over 10,705 active = 72.6% "failed" the 73% gate
            # while true coverage over price-covered symbols was 91.9%. Use symbols that
            # actually have prices on the technical max date as the denominator.
            cur.execute(
                "SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = %s",
                (tech_data_date,),
            )
            price_row = cur.fetchone()
            price_symbol_count = int(price_row[0]) if price_row and price_row[0] else 0
            denominator = price_symbol_count if price_symbol_count > 0 else len(symbols)

            coverage_pct = round(100 * tech_symbol_count / denominator, 1)
            if coverage_pct < 73:
                logger.error(
                    f"[DEPENDENCY] technical_data_daily coverage is {coverage_pct}% "
                    f"({tech_symbol_count}/{denominator} price-covered symbols) - below 73% threshold"
                )
                return 1

            logger.info(
                f"[DEPENDENCY] technical_data_daily: {tech_symbol_count}/{denominator} price-covered "
                f"symbols ({coverage_pct}%), age {tech_data_age}d"
            )
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as dep_err:
        logger.error(f"[LOADER] Failed to validate technical_data_daily dependency: {dep_err}. Exit code 1 (ERROR).")
        return 1

    loader = SignalsDailyLoader()
    try:
        result = loader.run(symbols, parallelism=args.parallelism)
        rows_inserted = result.get("rows_inserted", 0)
        logger.info(f"[LOADER] Daily signals load completed: {rows_inserted} rows inserted. Exit code 0 (SUCCESS).")

        # CLARIFICATION (Session 438): Technical data enrichment is TRULY OPTIONAL.
        # Technical indicators (SMA, ATR, RSI, MACD, etc.) are populated by load_technical_indicators.py,
        # not by enrichment. The enrichment module (enrich_buy_sell_daily_technical) would provide
        # additional optional data if it exists, but signals are fully functional without it.
        # The module doesn't exist in the codebase, so this try/except always falls through.
        logger.info("[LOADER] Checking for optional technical data enrichment module...")
        try:
            from loaders.enrich_buy_sell_daily_technical import enrich_technical_data

            try:
                enrich_result = enrich_technical_data(
                    since=today_et - timedelta(days=3), symbols=None, min_success_rate=0.95
                )
                logger.info(
                    f"[LOADER] Technical enrichment complete: {enrich_result['updated']} updated, "
                    f"{enrich_result['checked']} checked, {enrich_result['nulls_remaining']} nulls remaining"
                )
            except RuntimeError as e:
                # Enrichment module exists but failed to meet quality threshold - log and continue
                logger.warning(f"[LOADER] Technical data enrichment failed quality check: {e}. Continuing without enrichment.")
        except ImportError:
            # Enrichment module not available - this is expected, it's optional infrastructure
            logger.debug("[LOADER] Optional enrichment module not found. Signals generated from technical_data_daily only.")

        # SANITY CHECK (Session 267 FIX, hardened 2026-07-26): Detect signal count degradation
        # BEFORE marking loader COMPLETED. See _check_signal_degradation() docstring for the
        # all-time-average bug this replaced.
        try:
            with DatabaseContext("read") as cur:
                _check_signal_degradation(cur)
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as sanity_check_err:
            logger.warning(f"[SANITY_CHECK] Could not validate signal count: {sanity_check_err}. Continuing.")

        # CRITICAL FIX: Only advance watermark if records were actually loaded
        # BLOCKER #3 FIX: Prevent watermark advancement on zero-record days (weekends/holidays)
        # If rows_inserted=0, we loaded zero signals (weekend/holiday), so don't mark as completed
        # This prevents watermark from advancing and skipping the next trading day's signals
        if rows_inserted > 0:
            # CRITICAL FIX: Update loader status to COMPLETED with actual latest_date from table
            # Bug fix: Use MAX(date) from buy_sell_daily, not calendar date (today_et)
            # Root cause: Reporting today's calendar date when signals may only be generated through yesterday
            try:
                with DatabaseContext("read") as cur:
                    cur.execute("SET statement_timeout = 0")
                    # Get actual maximum date from buy_sell_daily (signals generated up to this date)
                    cur.execute("SELECT COALESCE(MAX(date), %s) FROM buy_sell_daily", (today_et,))
                    date_result = cur.fetchone()
                    if not date_result:
                        raise RuntimeError("CRITICAL: Failed to query max date from buy_sell_daily")
                    actual_max_date = date_result[0]

                    # CRITICAL FIX (Session 56): Calculate completion threshold based on upstream data quality
                    # buy_sell_daily inherits incompleteness from technical_data_daily (which covers ~4,750 of 10,549 universe)
                    # If technical_data_daily is 95% complete on this date, buy_sell_daily should accept 92%+ (3% margin)
                    # This prevents false FAILED statuses when upstream data is legitimately incomplete
                    cur.execute("""
                        WITH tech_coverage AS (
                            SELECT COUNT(DISTINCT symbol) as symbol_count FROM technical_data_daily WHERE date = %s
                        ),
                        tech_universe AS (
                            SELECT symbol_count FROM data_loader_status WHERE table_name = 'technical_data_daily'
                        )
                        SELECT
                            CASE WHEN t.symbol_count > 0 AND u.symbol_count > 0
                                 THEN (t.symbol_count::float / u.symbol_count * 100.0)
                                 ELSE 100.0
                            END as tech_coverage_pct
                        FROM tech_coverage t CROSS JOIN tech_universe u
                    """, (actual_max_date,))

                    result = cur.fetchone()
                    tech_coverage_pct = result[0] if result else 100.0
                    # Allow buy_sell_daily to be 3% lower than upstream technical_data_daily coverage (signal generation overhead)
                    min_threshold = max(90.0, tech_coverage_pct - 3.0)
                    logger.info(
                        f"[COMPLETION_THRESHOLD] Technical_data_daily coverage: {tech_coverage_pct:.1f}%. "
                        f"Setting buy_sell_daily threshold to {min_threshold:.1f}% (upstream coverage - 3% margin)"
                    )

                # Use LoaderStatusManager to consolidate status writes
                status_manager = LoaderStatusManager(table_name="buy_sell_daily")
                status_manager.mark_completed(latest_date=actual_max_date, min_completion_pct=min_threshold)
                logger.info(
                    f"[STATUS] Updated buy_sell_daily status to COMPLETED with latest_date={actual_max_date} (actual table max, not calendar date)"
                )
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as status_err:
                logger.error(f"[STATUS] Could not update loader status: {status_err}")
                return 1
        else:
            logger.info(
                f"[STATUS] Skipping watermark advance: zero signals loaded on {today_et} (likely weekend/holiday). "
                f"Watermark will NOT advance, next run will retry this date."
            )

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
