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
from typing import List, Optional

import psycopg2.sql

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
            now_utc = datetime.now(timezone.utc)
            now_et = now_utc.astimezone(EASTERN_TZ)
            end = now_et.date()

            while end > date(2020, 1, 1) and not MarketCalendar.is_trading_day(end):
                end = end - timedelta(days=1)

            with DatabaseContext("read") as cur:
                # Use the most recent date with price_daily data, not just the market calendar date
                cur.execute(
                    "SELECT MAX(date) FROM price_daily WHERE date <= %s",
                    (end,),
                )
                price_max_date_row = cur.fetchone()
                price_max_date = price_max_date_row[0] if price_max_date_row and price_max_date_row[0] else None

                # If there's no price data on the calculated end date, use the most recent available
                if price_max_date:
                    end = price_max_date

                cur.execute(
                    "SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = %s",
                    (end,),
                )
                price_row = cur.fetchone()
                price_coverage_symbols = price_row[0] if price_row else 0

                cur.execute(
                    "SELECT COUNT(DISTINCT symbol), MAX(date) FROM technical_data_daily WHERE date = %s",
                    (end,),
                )
                tech_row = cur.fetchone()
                tech_coverage_symbols = tech_row[0] if tech_row else 0
                tech_max_date = tech_row[1] if tech_row else None

                # ROOT CAUSE #5 FIX: Read global watermark once instead of per-symbol
                # Prevents 10k+ duplicate queries (one per symbol in fetch_incremental)
                cur.execute(
                    "SELECT MAX(date) FROM buy_sell_daily",
                )
                watermark_row = cur.fetchone()
                watermark_date = watermark_row[0] if watermark_row and watermark_row[0] else None

            today_et = now_et.date()
            tech_data_age = (today_et - tech_max_date).days if tech_max_date else None

            self._batch_context = {
                "end_date": end,
                "price_coverage_symbols": price_coverage_symbols,
                "tech_coverage_symbols": tech_coverage_symbols,
                "tech_data_age": tech_data_age,
                "watermark_date": watermark_date,
            }
            logger.debug(
                f"Batch context: end={end}, price_coverage={price_coverage_symbols}, "
                f"tech_coverage={tech_coverage_symbols}"
            )
        except Exception as e:
            logger.warning(f"Batch context preparation failed: {e}")
            self._batch_context = {}

    def fetch_incremental(self, symbol: str, since: date | None):
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
        # Read symbol-specific watermark from buy_sell_daily table to avoid regenerating signals.
        # BUGFIX: Use per-symbol watermark, not global watermark. Different symbols generate signals
        # on different schedules - some may have max_date=2026-06-03, others 2026-06-17.
        # Using global watermark caused symbols like AAPL to be skipped even when behind.
        if since is None:
            try:
                with DatabaseContext("read") as cur:
                    cur.execute(
                        "SELECT MAX(date) FROM buy_sell_daily WHERE symbol = %s",
                        (symbol,),
                    )
                    row = cur.fetchone()
                    if row and row[0]:
                        max_date = row[0]
                        # Handle different date types from database
                        if isinstance(max_date, date) and not isinstance(max_date, datetime):
                            since = max_date
                        elif isinstance(max_date, datetime):
                            since = max_date.date()
                        else:
                            # Try string conversion as fallback
                            since = date.fromisoformat(str(max_date).split(' ')[0])
            except Exception as e:
                logger.debug(f"Could not read buy_sell_daily watermark for {symbol}: {e}")
                # Fallback to global watermark if query fails
                watermark_date = (
                    self._batch_context.get("watermark_date")
                    if self._batch_context
                    else None
                )
                if watermark_date:
                    since = (
                        watermark_date
                        if isinstance(watermark_date, date)
                        else date.fromisoformat(str(watermark_date))
                    )

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
                tech_count = cur.fetchone()[0]

                if tech_count == 0:
                    # Fallback: Use most recent technical data available (safe for signal generation)
                    # Signal generation doesn't require exact date match - closest recent data is valid
                    cur.execute(
                        "SELECT MAX(date) FROM technical_data_daily WHERE symbol = %s AND date < %s",
                        (symbol, end),
                    )
                    fallback_date = cur.fetchone()[0]
                    if fallback_date:
                        days_back = (end - fallback_date).days
                        logger.debug(
                            f"{symbol}: Using technical data from {fallback_date} ({days_back} days back) for signal generation"
                        )
                        end = fallback_date
                    else:
                        # Technical data is missing entirely - log rejection
                        self._log_rejection_if_available(
                            symbol, end, "technical_data_missing"
                        )
                        logger.warning(
                            f"{symbol}: Technical data missing for {end} - signals cannot be generated"
                        )
                        return []

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
                price_coverage_symbols = (
                    self._batch_context.get("price_coverage_symbols", 0)
                    if self._batch_context
                    else 0
                )
                tech_coverage_symbols = (
                    self._batch_context.get("tech_coverage_symbols", 0)
                    if self._batch_context
                    else 0
                )

                # Require at least 3000 symbols with prices before generating signals
                if price_coverage_symbols < 3000:
                    logger.warning(
                        f"{symbol}: price_daily incomplete for {end}: only "
                        f"{price_coverage_symbols} symbols (expected >= 3000). "
                        "Rejecting all signals until stock_prices_daily completes."
                    )
                    self._log_rejection_if_available(
                        symbol, end, "price_daily_incomplete_coverage"
                    )
                    return []
                # Technical coverage relative to price coverage (normal: 80-83%)
                tech_coverage = (
                    (tech_coverage_symbols / price_coverage_symbols * 100)
                    if price_coverage_symbols > 0
                    else 0
                )

                # Warn if technical data covers < 70% of price symbols (normal is 80-83%)
                # RESILIENCE FIX: Allow signal generation to proceed even with incomplete technical data.
                # Technical columns will be backfilled by enrich_buy_sell_daily_technical.py after loader completes.
                # This prevents rejection of all signals when upstream loader is slow or partially failed.
                if tech_coverage < 70:
                    logger.warning(
                        f"{symbol}: technical_data_daily incomplete for {end}: "
                        f"{tech_coverage_symbols}/{price_coverage_symbols} price symbols "
                        f"({tech_coverage:.1f}%, expected >= 70%). "
                        "Proceeding with signal generation - technical data will be backfilled later."
                    )
                    # Do NOT return [] — allow signals to be generated even without complete technical data
                    # The enrichment script will populate technical columns afterward
        except Exception as e:
            logger.warning(f"{symbol}: Technical data check failed: {e}")
            return []

        # Fetch required data for signal generation
        rows = self._fetch_signal_data(symbol, start, end)
        if not rows:
            logger.warning(
                f"{symbol}: No technical data found between {start} and {end}"
            )
            return []

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

    def _calculate_data_source_age_days(
        self, symbol: str, source_table: str
    ) -> int | None:
        """Calculate age of most recent data in source table (in days).

        Returns:
            Days since most recent row in source table, or None if no data
        """
        try:
            with DatabaseContext("read") as cur:
                table_safe = assert_safe_table(source_table)
                cur.execute(
                    psycopg2.sql.SQL(
                        "SELECT MAX(date) FROM {} WHERE symbol = %s"
                    ).format(psycopg2.sql.Identifier(table_safe)),
                    (symbol,),
                )
                row = cur.fetchone()
                if row and row[0]:
                    max_date = (
                        row[0]
                        if isinstance(row[0], date)
                        else date.fromisoformat(str(row[0]))
                    )
                    # FIX: Use ET date, not system date (AWS runs in UTC but trading is ET-based)
                    today_et = datetime.now(EASTERN_TZ).date()
                    age_days = (today_et - max_date).days
                    return age_days
        except Exception as e:
            logger.warning(f"Could not calculate {source_table} age for {symbol}: {e}")
        return None

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
                    ("buy_sell_daily", reason, symbol, signal_date, "loader"),
                )
        except Exception as e:
            logger.debug(
                f"[SIGNAL_REJECTION_LOG] Could not log rejection for {symbol}: {e}"
            )

    def _fetch_signal_data(self, symbol: str, start: date, end: date) -> list[dict]:
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
                            f"{symbol} [{r[0]}]: Row dropped — missing required field "
                            f"(date={r[0]}, close={r[11]})"
                        )
                        continue
                    rows.append(
                        {
                            "date": r[0].isoformat() if r[0] else None,
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
                    logger.warning(
                        f"{symbol}: Dropped {dropped_rows} row(s) due to missing date or close price"
                    )
                return rows
        except Exception as e:
            logger.error(f"Failed to fetch signal data for {symbol}: {e}")
            return []

    def _generate_signals(self, symbol: str, rows: list[dict]) -> list[dict]:
        """Generate buy/sell signals matching Pine Script pivot-breakout logic.

        BUY: High > recent_swing_high AND close > SMA50 (breakout above pivot with trend filter)
        SELL: Low < recent_swing_low (stop loss trigger)
        """
        if not rows:
            return []

        # Use batch-cached tech data age (computed once for all symbols, not per-symbol query)
        tech_data_age = (self._batch_context or {}).get("tech_data_age")

        signals = []
        skipped_count = 0

        for i, row in enumerate(rows):
            high = row.get("high")
            low = row.get("low")
            close = row.get("close")
            sma_50 = row.get("sma_50")
            sma_200 = row.get("sma_200")
            volume = row.get("volume")
            atr = row.get("atr")
            rsi = row.get("rsi")
            macd = row.get("macd")
            macd_signal = row.get("macd_signal")
            ema_21 = row.get("ema_21")
            adx = row.get("adx")
            mansfield_rs = row.get("mansfield_rs")

            if close is None or high is None or low is None:
                skipped_count += 1
                logger.debug(
                    f"{symbol} [{row.get('date')}]: Skipping row — missing required OHLC field "
                    f"(close={close}, high={high}, low={low})"
                )
                continue

            signal_type = None
            strength = 0.0
            reason = ""
            buylevel = None
            stoplevel = None

            # Find most recent swing high (3-bar pivot: high > high[i-3:i] AND high > high[i+1:i+4])
            # Use 20-bar lookback for swing trading (captures swings over 3-4 weeks)
            recent_swing_high = None
            swing_high_sma50 = None
            for j in range(max(0, i - 20), i):
                candidate = rows[j].get("high")
                if not candidate:
                    continue
                # Require complete data: all lookback and lookforward bars must have valid highs
                lookback_bars = [rows[k].get("high") for k in range(max(0, j - 3), j)]
                lookforward_bars = [
                    rows[k].get("high") for k in range(j + 1, min(len(rows), j + 4))
                ]
                if not all(lookback_bars) or not all(lookforward_bars):
                    continue
                # Validate pivot: candidate must be higher than all lookback and lookforward bars
                if all(candidate > b for b in lookback_bars) and all(
                    candidate > b for b in lookforward_bars
                ):
                    if recent_swing_high is None or candidate > recent_swing_high:
                        recent_swing_high = candidate
                        swing_high_sma50 = rows[j].get(
                            "sma_50"
                        )  # SMA50 at the time swing high formed

            # Find most recent swing low (3-bar pivot: low < low[i-3:i] AND low < low[i+1:i+4])
            # Use 10-bar lookback for swing lows (more reactive stop loss, not stale entries)
            recent_swing_low = None
            for j in range(max(0, i - 10), i):
                candidate = rows[j].get("low")
                if not candidate:
                    continue
                # Require complete data: all lookback and lookforward bars must have valid lows
                lookback_bars = [rows[k].get("low") for k in range(max(0, j - 3), j)]
                lookforward_bars = [
                    rows[k].get("low") for k in range(j + 1, min(len(rows), j + 4))
                ]
                if not all(lookback_bars) or not all(lookforward_bars):
                    continue
                # Validate pivot: candidate must be lower than all lookback and lookforward bars
                if all(candidate < b for b in lookback_bars) and all(
                    candidate < b for b in lookforward_bars
                ):
                    if recent_swing_low is None or candidate < recent_swing_low:
                        recent_swing_low = candidate

            # BUY: Breakout above swing high where swing_high > SMA50 (trend filter on pivot level, not current bar)
            if (
                recent_swing_high
                and swing_high_sma50
                and high > recent_swing_high
                and recent_swing_high > swing_high_sma50
            ):
                signal_type = "BUY"
                breakout_pct = (
                    ((high - recent_swing_high) / recent_swing_high * 100)
                    if recent_swing_high > 0
                    else 0
                )
                strength = min(0.5 + (breakout_pct / 5.0), 1.0)
                reason = f"Breakout above swing high ({abs(breakout_pct):.1f}%) with price > SMA50"
                buylevel = round(recent_swing_high, 4)
                stoplevel = (
                    round(recent_swing_low, 4)
                    if recent_swing_low
                    else round(close * 0.92, 4)
                )

            # SELL: Breakdown below swing low (stop loss)
            elif recent_swing_low and low < recent_swing_low:
                signal_type = "SELL"
                breakdown_pct = (
                    ((recent_swing_low - low) / recent_swing_low * 100)
                    if recent_swing_low > 0
                    else 0
                )
                strength = min(0.5 + (breakdown_pct / 5.0), 1.0)
                reason = f"Breakdown below swing low ({abs(breakdown_pct):.1f}%)"
                buylevel = round(close, 4)
                stoplevel = round(close * 1.08, 4)

            if signal_type:
                # Compute volume surge: compare to 20-bar average volume
                vol_surge = None
                volume_surge_capped = False
                decimal84_max = 9999.9999
                if volume is not None and i >= 5:
                    recent_vols = [
                        rows[j].get("volume")
                        for j in range(max(0, i - 20), i)
                        if rows[j].get("volume") is not None
                    ]
                    if recent_vols:
                        avg_vol = sum(recent_vols) / len(recent_vols)  # type: ignore[arg-type]
                        if avg_vol > 0:
                            raw_surge = (volume / avg_vol - 1) * 100
                            if raw_surge > decimal84_max:
                                volume_surge_capped = True
                            vol_surge = round(min(raw_surge, decimal84_max), 2)

                # Compute 50-bar average volume
                avg_vol_50d = None
                if i >= 10:
                    vols_50 = [
                        rows[j].get("volume")
                        for j in range(max(0, i - 50), i)
                        if rows[j].get("volume") is not None
                    ]
                    if vols_50:
                        avg_vol_50d = int(sum(vols_50) / len(vols_50))  # type: ignore[arg-type]

                # Determine market stage from moving averages
                market_stage = None
                if close and sma_50 and sma_200:
                    if close > sma_50 > sma_200:
                        market_stage = "Stage 2"
                    elif close > sma_200 and close < sma_50:
                        market_stage = "Stage 1"
                    elif close < sma_50 < sma_200:
                        market_stage = "Stage 4"
                    elif close < sma_200 and close > sma_50:
                        market_stage = "Stage 3"

                # Entry/exit planning based on signal type
                risk_pct = 8.0
                if signal_type == "BUY" and close:
                    if buylevel is None:
                        buylevel = round(close, 4)
                    if stoplevel is None:
                        stoplevel = round(close * (1 - risk_pct / 100), 4)
                    initial_stop = stoplevel
                    trailing_stop = stoplevel
                    sell_level = stoplevel
                    pivot_price = buylevel
                    buy_zone_start = round(buylevel * 0.99, 4)
                    buy_zone_end = round(buylevel * 1.05, 4)
                    profit_target_8pct = round(buylevel * 1.08, 4)
                    profit_target_20pct = round(buylevel * 1.20, 4)
                    profit_target_25pct = round(buylevel * 1.25, 4)
                    exit_trigger_1 = profit_target_8pct
                    exit_trigger_2 = profit_target_20pct
                    rr = round(
                        (profit_target_20pct - buylevel)
                        / max(buylevel - stoplevel, 0.01),
                        2,
                    )
                elif signal_type == "SELL" and close:
                    if buylevel is None:
                        buylevel = round(close, 4)
                    if stoplevel is None:
                        stoplevel = round(close * (1 + risk_pct / 100), 4)
                    initial_stop = stoplevel
                    trailing_stop = stoplevel
                    sell_level = round(close, 4)
                    pivot_price = buylevel
                    buy_zone_start = None
                    buy_zone_end = None
                    profit_target_8pct = round(buylevel * 0.92, 4)
                    profit_target_20pct = round(buylevel * 0.80, 4)
                    profit_target_25pct = round(buylevel * 0.75, 4)
                    exit_trigger_1 = profit_target_8pct
                    exit_trigger_2 = profit_target_20pct
                    rr = round(
                        (buylevel - profit_target_20pct)
                        / max(stoplevel - buylevel, 0.01),
                        2,
                    )
                else:
                    initial_stop = trailing_stop = sell_level = pivot_price = None
                    buy_zone_start = buy_zone_end = None
                    profit_target_8pct = profit_target_20pct = profit_target_25pct = (
                        None
                    )
                    exit_trigger_1 = exit_trigger_2 = None
                    rr = None

                signals.append(
                    {
                        "symbol": symbol,
                        "date": row["date"],
                        "signal_triggered_date": row["date"],
                        "timeframe": "1d",
                        "signal": signal_type,
                        "signal_type": signal_type,
                        "strength": float(strength),
                        "reason": reason,
                        "entry_quality_score": None,
                        "signal_quality_score": None,
                        "volume_surge_pct": vol_surge,
                        "volume_surge_capped": volume_surge_capped,
                        "risk_reward_ratio": rr,
                        "risk_pct": risk_pct,
                        "rsi": float(rsi) if rsi is not None else None,
                        "sma_50": float(sma_50) if sma_50 is not None else None,
                        "sma_200": float(sma_200) if sma_200 is not None else None,
                        "ema_21": float(ema_21) if ema_21 is not None else None,
                        "atr": float(atr) if atr is not None else None,
                        "adx": float(adx) if adx is not None else None,
                        "mansfield_rs": (
                            float(mansfield_rs) if mansfield_rs is not None else None
                        ),
                        "macd": float(macd) if macd is not None else None,
                        "macd_signal": (
                            float(macd_signal) if macd_signal is not None else None
                        ),
                        "stage_number": None,
                        "market_stage": market_stage,
                        "open": row.get("open"),
                        "high": float(high) if high is not None else None,
                        "low": float(low) if low is not None else None,
                        "close": float(close) if close is not None else None,
                        "volume": volume,
                        "avg_volume_50d": avg_vol_50d,
                        "buylevel": buylevel,
                        "stoplevel": stoplevel,
                        "initial_stop": initial_stop,
                        "trailing_stop": trailing_stop,
                        "sell_level": sell_level,
                        "pivot_price": pivot_price,
                        "buy_zone_start": buy_zone_start,
                        "buy_zone_end": buy_zone_end,
                        "profit_target_8pct": profit_target_8pct,
                        "profit_target_20pct": profit_target_20pct,
                        "profit_target_25pct": profit_target_25pct,
                        "exit_trigger_1_price": exit_trigger_1,
                        "exit_trigger_2_price": exit_trigger_2,
                        "technical_data_age_days": tech_data_age,
                    }
                )

        if skipped_count > 0:
            logger.warning(
                f"{symbol}: Skipped {skipped_count} row(s) during signal generation "
                f"due to missing OHLC fields — {len(signals)} signal(s) generated"
            )
        return signals

    # Columns with DECIMAL(8,4) precision — max 9999.9999
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

    def transform(self, rows):
        """Cap DECIMAL(8,4) columns to prevent numeric field overflow on high-price stocks."""
        for row in rows:
            capped_cols = []
            for col in self._DECIMAL84_COLS:
                v = row.get(col)
                if (
                    v is not None
                    and isinstance(v, (int, float))
                    and abs(v) > self.decimal84_max
                ):
                    capped_cols.append(col)
                    row[col] = self.decimal84_max if v > 0 else -self.decimal84_max
            if capped_cols:
                row["_metrics_capped_at_db_limit"] = capped_cols
                logger.warning(
                    f"{row.get('symbol')} [{row.get('date')}]: Metrics capped at {self.decimal84_max}: {capped_cols}"
                )
        return rows


def main():
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
        logger.error(f"Failed to get symbols: {e}")
        return 1

    logger.info(
        f"Starting buy_sell_daily loader with {len(symbols)} symbols, parallelism={args.parallelism}"
    )

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
            # Verify stock_prices_daily is not stuck RUNNING/PENDING
            cur.execute(
                "SELECT status FROM data_loader_status WHERE table_name = 'stock_prices_daily'"
            )
            result = cur.fetchone()
            prices_status = result[0] if result else None
            if prices_status in ("RUNNING", "PENDING"):
                logger.warning(
                    f"[DEPENDENCY] Aborting buy_sell_daily: stock_prices_daily is {prices_status} - "
                    "waiting for price data to be available"
                )
                return 0  # Exit cleanly, will retry on next pipeline run
    except Exception as status_err:
        logger.warning(
            f"[DEPENDENCY] Could not check stock_prices_daily status: {status_err}"
        )

    # ISSUE #7: Validate dependency — technical_data_daily must be fresh and have good coverage
    try:
        with DatabaseContext("read") as cur:
            cur.execute("SELECT MAX(date) FROM technical_data_daily")
            result = cur.fetchone()
            if not result or not result[0]:
                logger.error(
                    "[DEPENDENCY] technical_data_daily is empty - cannot generate signals"
                )
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

            # Check coverage: technical_data_daily must have at least 75% symbol coverage
            cur.execute("""
                SELECT COUNT(DISTINCT symbol) FROM technical_data_daily
                WHERE date = (SELECT MAX(date) FROM technical_data_daily)
            """)
            cur_row = cur.fetchone()
            tech_symbol_count = cur_row[0] if cur_row else 0

            coverage_pct = (
                round(100 * tech_symbol_count / len(symbols), 1) if symbols else 0
            )
            if coverage_pct < 75:
                logger.error(
                    f"[DEPENDENCY] technical_data_daily coverage is {coverage_pct}% ({tech_symbol_count}/{len(symbols)} symbols) - below 75% threshold"
                )
                return 1

            logger.info(
                f"[DEPENDENCY] ✓ technical_data_daily: {tech_symbol_count}/{len(symbols)} symbols ({coverage_pct}%), age {tech_data_age}d"
            )
    except Exception as dep_err:
        logger.error(
            f"[DEPENDENCY] Failed to validate technical_data_daily dependency: {dep_err}"
        )
        return 1

    loader = SignalsDailyLoader()
    try:
        result = loader.run(symbols, parallelism=args.parallelism)
        logger.info("Daily signals load completed")

        # ISSUE #7 FIX: Automatically enrich technical data after signal generation
        # This backfills NULL technical columns in buy_sell_daily with data from technical_data_daily
        logger.info("Starting technical data enrichment...")
        from enrich_buy_sell_daily_technical import enrich_technical_data

        enrich_result = enrich_technical_data(
            since=today_et - timedelta(days=3), symbols=None
        )
        logger.info(
            f"Technical enrichment complete: {enrich_result['updated']} updated, {enrich_result['checked']} checked"
        )

        return 0
    except Exception as e:
        logger.error(f"Daily signals load failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
