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

import psycopg2.sql

from loaders.buy_signal_generation_handler import BuySignalGenerationHandler
from utils.db.context import DatabaseContext
from utils.db.sql_safety import assert_safe_table
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
            # Check signal_quality_scores availability — warn but don't block.
            # On initial bootstrap, quality scores don't exist yet; buy_sell_daily must run
            # first so signal_quality_scores can evaluate its output. Signals will have NULL
            # quality scores on first run; a subsequent SQS run backfills them.
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT status FROM data_loader_status WHERE table_name = %s",
                    ("signal_quality_scores",),
                )
                sqs_status = cur.fetchone()
                if not sqs_status:
                    logger.warning(
                        "signal_quality_scores loader has not run yet. "
                        "Buy/sell signals will have NULL quality scores until SQS backfill completes. "
                        "This is expected on first run; subsequent runs will have quality validation."
                    )
                elif sqs_status[0] not in ("COMPLETED", "success", "OK"):
                    raise RuntimeError(
                        f"signal_quality_scores loader failed with status '{sqs_status[0]}' (not COMPLETED). "
                        "Cannot generate buy/sell signals without quality validation. "
                        "Signal validation is CRITICAL for trading decisions. "
                        "Upstream loader must complete successfully before signal generation can proceed."
                    )

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
                # Use the most recent date with price_daily data, not just the market calendar date
                cur.execute(
                    "SELECT MAX(date) FROM price_daily WHERE date <= %s",
                    (end,),
                )
                price_max_date_row = cur.fetchone()
                if price_max_date_row is None:
                    raise RuntimeError(
                        f"CRITICAL: price_daily query returned None for {end}. "
                        "Query malformed or price_daily table empty. Cannot determine end date for signal generation."
                    )
                if len(price_max_date_row) < 1:
                    raise RuntimeError(
                        f"CRITICAL: price_daily query returned invalid row structure. "
                        f"Expected at least 1 column, got {len(price_max_date_row)}."
                    )
                price_max_date = price_max_date_row[0]

                # If there's no price data on the calculated end date, use the most recent available
                if price_max_date:
                    end = price_max_date

                cur.execute(
                    "SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = %s",
                    (end,),
                )
                price_row = cur.fetchone()
                if price_row is None:
                    raise RuntimeError(
                        f"CRITICAL: price_daily coverage query returned None for {end}. "
                        "Query malformed. Cannot validate price data availability."
                    )
                if len(price_row) < 1:
                    raise RuntimeError(
                        f"CRITICAL: price_daily coverage query returned invalid row structure. "
                        f"Expected at least 1 column, got {len(price_row)}."
                    )
                if price_row[0] is None:
                    raise RuntimeError(
                        f"CRITICAL: Price data count is NULL for {end}. "
                        "Database query returned invalid data. Cannot generate signals."
                    )
                price_coverage_symbols = int(price_row[0])
                if price_coverage_symbols == 0:
                    raise RuntimeError(
                        f"CRITICAL: No price data found for {end}. "
                        "Upstream loader failed. Cannot generate signals without price data."
                    )

                cur.execute(
                    "SELECT COUNT(DISTINCT symbol), MAX(date) FROM technical_data_daily WHERE date = %s",
                    (end,),
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
                        f"CRITICAL: No symbols found in technical_data_daily for {end}. "
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
        from datetime import datetime, timezone

        from algo.infrastructure import MarketCalendar

        # ROOT CAUSE #4 FIX: Use cached end_date from batch context (computed once for all symbols)
        # instead of recomputing and re-verifying trading day for each symbol.
        # This eliminates per-symbol timezone and trading day calculations.
        if self._batch_context and "end_date" in self._batch_context:
            end = self._batch_context["end_date"]
        else:
            # Fallback if batch context unavailable
            now_utc = datetime.now(timezone.utc)
            now_et = now_utc.astimezone(EASTERN_TZ)
            end = now_et.date()
            while end > date(2020, 1, 1) and not MarketCalendar.is_trading_day(end):
                end = end - timedelta(days=1)

        # On ECS restart the in-memory watermark is empty, so since=None.
        # ISSUE #9 FIX: Look up symbol watermark from pre-cached batch_context
        # (populated at startup with all symbols' watermarks in one query).
        # Fallback to database query only on cache miss (for newly added symbols).
        # This prevents stalls on ECS restart when fetching per-symbol watermarks.
        #
        # BUGFIX: Use per-symbol watermark, not global watermark. Different symbols generate signals
        # on different schedules - some may have max_date=2026-06-03, others 2026-06-17.
        # Using global watermark caused symbols like AAPL to be skipped even when behind.
        if since is None:
            try:
                # Try cache first (populated in _prepare_batch_context)
                if not self._batch_context:
                    logger.debug(
                        f"[WATERMARK] {symbol}: Batch context not initialized - "
                        "falling back to database query for watermark"
                    )
                    symbol_watermarks = None
                else:
                    symbol_watermarks = self._batch_context.get("symbol_watermarks")
                    if symbol_watermarks is None:
                        logger.debug(
                            f"[WATERMARK] {symbol}: 'symbol_watermarks' missing from batch context - "
                            "falling back to database query"
                        )

                max_date = None
                if symbol_watermarks is not None and isinstance(symbol_watermarks, dict):
                    max_date = symbol_watermarks.get(symbol)
                    if max_date is None:
                        logger.debug(
                            f"[WATERMARK] {symbol}: Not found in cached symbol_watermarks - "
                            "likely newly added symbol, querying database"
                        )

                # Cache miss: query database as fallback
                if max_date is None:
                    logger.debug(f"[WATERMARK] {symbol}: Querying database for watermark (cache miss)")
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
                # First, verify technical_data_daily has sufficient data for symbol on end date
                cur.execute(
                    "SELECT COUNT(*) FROM technical_data_daily WHERE symbol = %s AND date = %s",
                    (symbol, end),
                )
                row = cur.fetchone()
                if row is None or row[0] is None:
                    raise RuntimeError(f"Technical count query failed for {symbol} on {end}")
                tech_count = row[0]

                if tech_count == 0:
                    raise RuntimeError(
                        f"[BUY_SELL_DAILY] {symbol}: No technical data for {end}. "
                        "Technical data is CRITICAL for buy/sell signal generation. "
                        "Coverage validation passed (≥70% overall), but this symbol has no data. "
                        "Indicates incomplete upstream loader or data corruption. Cannot proceed."
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

                # Require at least 3000 symbols with prices before generating signals
                if price_coverage_symbols < 3000:
                    raise RuntimeError(
                        f"{symbol}: price_daily incomplete for {end}: only "
                        f"{price_coverage_symbols} symbols (expected >= 3000). "
                        "Cannot generate signals without sufficient price data coverage. "
                        "Verify price_daily loader completed successfully."
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

        # Fetch required data for signal generation
        rows = self._fetch_signal_data(symbol, start, end)
        if not rows:
            raise RuntimeError(
                f"[BUY_SELL_DAILY] {symbol}: _fetch_signal_data returned no rows for {start} to {end}. "
                "Technical and price data are CRITICAL for buy/sell signal generation. "
                "Upstream loaders (technical_data_daily, price_daily) may be incomplete or corrupted. "
                "Cannot generate signals without complete data coverage."
            )

        # Generate signals
        signals = self._generate_signals(symbol, rows)

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

    def _calculate_data_source_age_days(self, symbol: str, source_table: str) -> int | None:
        """Calculate age of most recent data in source table (in days).

        Returns:
            Days since most recent row in source table, or None if no data
        """
        try:
            with DatabaseContext("read") as cur:
                table_safe = assert_safe_table(source_table)
                cur.execute(
                    psycopg2.sql.SQL("SELECT MAX(date) FROM {} WHERE symbol = %s").format(
                        psycopg2.sql.Identifier(table_safe)
                    ),
                    (symbol,),
                )
                row = cur.fetchone()
                if row is None or len(row) < 1 or row[0] is None:
                    logger.debug(
                        f"[DATA_AGE] {symbol}: No data in {source_table} - data unavailable for age calculation"
                    )
                    return None
                max_date_val = row[0]
                if isinstance(max_date_val, date) and not isinstance(max_date_val, datetime):
                    max_date = max_date_val
                elif isinstance(max_date_val, datetime):
                    max_date = max_date_val.date()
                elif isinstance(max_date_val, str):
                    try:
                        max_date = date.fromisoformat(max_date_val)
                    except ValueError as e:
                        raise RuntimeError(
                            f"[DATA_AGE] {symbol}: Invalid date format in {source_table}: {max_date_val!r}. "
                            "Cannot calculate data age without valid date."
                        ) from e
                else:
                    raise RuntimeError(
                        f"[DATA_AGE] {symbol}: Unexpected type for {source_table} date: {type(max_date_val).__name__}. "
                        f"Expected date or string, got {max_date_val!r}. Database query may return corrupted data."
                    )
                # FIX: Use ET date, not system date (AWS runs in UTC but trading is ET-based)
                today_et = datetime.now(EASTERN_TZ).date()
                age_days = (today_et - max_date).days
                return age_days
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"[DATA_AGE] {symbol}: Failed to calculate data age from {source_table}: {e}. "
                "Cannot verify data freshness without source table access."
            ) from e

    def get_tech_data_age(self) -> float | None:
        """Return current batch tech_data_age for signal generation.

        Facade elimination: public getter for _batch_context['tech_data_age']
        used by SignalsDailyLoaderFacade to eliminate private member access.

        Returns:
            Age in days (float), or None if batch context unavailable.
            Explicitly logs when batch context is missing (data unavailable).
        """
        if not self._batch_context:
            logger.debug("[TECH_DATA_AGE] Batch context not initialized - tech data age unavailable")
            return None

        tech_data_age = self._batch_context.get("tech_data_age")
        if tech_data_age is None:
            logger.debug("[TECH_DATA_AGE] 'tech_data_age' not in batch context - technical data freshness unavailable")
        return tech_data_age

    def _log_rejection_if_available(self, symbol: str, signal_date: date, reason: str) -> None:
        """Log signal rejection to signal_rejection_log for observability (non-fatal)."""
        try:
            with DatabaseContext("write") as cur:
                cur.execute(
                    """
                    INSERT INTO signal_rejection_log
                    (signal_source_table, rejection_reason, symbol, signal_date, rejected_at_tier, created_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                """,
                    ("buy_sell_daily", reason, symbol, signal_date, "loader"),
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.debug(f"[SIGNAL_REJECTION_LOG] Could not log rejection for {symbol}: {e}")

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
        handler = BuySignalGenerationHandler(self)

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
        """Cap DECIMAL(8,4) columns to prevent numeric field overflow on high-price stocks."""
        for row in rows:
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
                logger.warning("No symbols found in stock_symbols table - exiting")
                return 1
    except Exception as e:
        raise RuntimeError(f"Failed to fetch active symbols: {e}. Cannot proceed without symbol list.") from e

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
        raise RuntimeError(
            f"CRITICAL: Failed to check price_daily status: {status_err}. "
            "Cannot verify upstream loader is ready. Aborting to prevent silent dependency failure."
        ) from status_err

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
                raise RuntimeError(
                    "[DEPENDENCY] Symbol list is empty. Cannot calculate coverage percentage. "
                    "Check stock_symbols table and active symbol configuration."
                )

            cur.execute("""
                SELECT COUNT(DISTINCT symbol) FROM technical_data_daily
                WHERE date = (SELECT MAX(date) FROM technical_data_daily)
            """)
            cur_row = cur.fetchone()
            if cur_row is None or len(cur_row) < 1:
                raise RuntimeError(
                    "CRITICAL: Failed to count technical_data_daily symbols. "
                    "Query returned invalid row structure. Cannot verify coverage."
                )
            if cur_row[0] is None:
                raise RuntimeError(
                    "CRITICAL: technical_data_daily symbol count query returned NULL. "
                    "Database query or upstream loader may have failed."
                )
            tech_symbol_count = int(cur_row[0])
            if tech_symbol_count == 0:
                raise RuntimeError(
                    "CRITICAL: No symbols found in technical_data_daily on latest date. "
                    "Upstream loader failed or data missing. Cannot generate signals."
                )

            coverage_pct = round(100 * tech_symbol_count / len(symbols), 1)
            if coverage_pct < 75:
                logger.error(
                    f"[DEPENDENCY] technical_data_daily coverage is {coverage_pct}% ({tech_symbol_count}/{len(symbols)} symbols) - below 75% threshold"
                )
                return 1

            logger.info(
                f"[DEPENDENCY] ✓ technical_data_daily: {tech_symbol_count}/{len(symbols)} symbols ({coverage_pct}%), age {tech_data_age}d"
            )
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as dep_err:
        raise RuntimeError(
            f"[DEPENDENCY] Failed to validate technical_data_daily dependency: {dep_err}. "
            "Buy/sell signals require technical data availability."
        ) from dep_err

    loader = SignalsDailyLoader()
    try:
        result = loader.run(symbols, parallelism=args.parallelism)
        logger.info("Daily signals load completed")

        # ISSUE #27 FIX: Make technical data enrichment part of the critical path.
        # Enrichment is MANDATORY for signal quality-if it fails, the entire load fails.
        # This prevents buy_sell_daily from being marked COMPLETED with NULL technical fields.
        # Fail-close: If >5% of records can't be enriched, update loader status to FAILED.
        logger.info("Starting technical data enrichment (fail-close)...")
        from enrich_buy_sell_daily_technical import enrich_technical_data

        try:
            enrich_result = enrich_technical_data(
                since=today_et - timedelta(days=3), symbols=None, min_success_rate=0.95
            )
            logger.info(
                f"✓ Technical enrichment complete: {enrich_result['updated']} updated, "
                f"{enrich_result['checked']} checked, {enrich_result['nulls_remaining']} nulls remaining"
            )
        except RuntimeError as e:
            # Enrichment failed to meet quality threshold - mark loader as FAILED
            logger.critical(f"[ENRICHMENT_FAILED] {e!s}")
            try:
                # Update loader status to FAILED so orchestration detects the failure
                with DatabaseContext("write") as cur:
                    cur.execute("SET statement_timeout = 0")
                    cur.execute(
                        "UPDATE data_loader_status SET status = %s, last_updated = NOW() WHERE table_name = %s",
                        ("FAILED", "buy_sell_daily"),
                    )
                    logger.info("[STATUS] Marked buy_sell_daily as FAILED due to enrichment failure")
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as status_err:
                logger.error(f"[STATUS] Could not update loader status: {status_err}")

            raise RuntimeError(
                f"[ENRICHMENT_CRITICAL] Technical data enrichment failed. "
                f"Marked buy_sell_daily loader as FAILED to prevent silent data corruption. "
                f"Signal quality would be degraded with NULL technical fields. "
                f"Details: {e!s}"
            ) from e

        return 0
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        raise RuntimeError(f"Daily signals load failed: {e}") from e


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as e:
        logger.error(str(e))
        sys.exit(1)
