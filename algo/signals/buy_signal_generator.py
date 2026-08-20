#!/usr/bin/env python3
"""Buy/sell signal generation - Swing pivot breakout logic.

Handles:
- Swing pivot detection (highs and lows)
- Signal generation logic (BUY/SELL triggers)
- Volume metrics and market stage computation
- Entry/exit level calculation

This is the single source of truth for buy/sell signal generation.
Used by: loaders/load_buy_sell_daily.py, orchestrator Phase 7, backtesting.
"""

import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

logger = logging.getLogger(__name__)

# Signal generation thresholds
# 2026-08-19: got the actual TradingView Pine source (user-provided) and checked it against
# this file line by line. Pine's swing high/low (`valuewhen(pvthi_, high[pvtLenR], 0)`) has NO
# fixed lookback window at all - ta.pivothigh/pivotlow with leftbars=rightbars=3 confirm a pivot
# 3 bars after it forms, and that level then persists *indefinitely* (via valuewhen/fixnan)
# until a newer pivot replaces it, no matter how many bars ago it was set. A prior fix in this
# file (restoring a "Pine-calibrated" 20-bar/10-bar window, replacing an unverified 50-bar one)
# was itself wrong - there is no such window in the real strategy; any fixed bar count is a
# deviation. These constants now exist ONLY as the last-resort STRATEGY 3 fallback bound (for
# data-quality robustness on symbols with gaps - not part of the authentic Pine logic at all);
# STRATEGY 1/2 (the actual Pine-equivalent path) search all available history.
SWING_HIGH_LOOKBACK_BARS = 20
SWING_LOW_LOOKBACK_BARS = 10

# Internal classify_base_type() pattern names -> display strings used by the frontend
# (webapp/frontend/src/pages/TradingSignals.jsx BASE_TYPE_VARIANT / badges).
_BASE_TYPE_DISPLAY = {
    "cup_with_handle": "Cup w/ Handle",
    "flat_base": "Flat Base",
    "double_bottom": "Double Bottom",
    "ascending_base": "Ascending Base",
    "vcp": "VCP",
    "saucer": "Saucer",
    "consolidation": "Consolidation",
    "wide_and_loose": "Wide & Loose",
}


class BuySignalGenerator:
    def __init__(self) -> None:
        self._pattern_classifier: Any = None

    def run(self, symbol: str, rows: list[dict[str, Any]], tech_data_age: int | None = None) -> list[dict[str, Any]]:
        """Generate buy/sell signals from technical indicator data.

        Args:
            symbol: Ticker symbol
            rows: List of technical data rows with OHLCV and indicators
            tech_data_age: Optional age of technical data in days

        Returns:
            List of signal dicts with entry/exit levels and metrics

        Raises:
            RuntimeError: If technical data is unavailable (required for signal generation)
            ValueError: If data quality is insufficient (<80% complete OHLCV)
        """
        if not rows:
            raise RuntimeError(
                f"[SIGNAL_GENERATION_MISSING_DATA] Cannot generate buy/sell signals for {symbol}: "
                f"technical data unavailable. Signal generation requires OHLCV and indicator values."
            )

        # Fail-fast: Validate data quality before processing
        # Pivot detection requires ~80% completeness of OHLC data to be reliable
        required_fields = ["open", "high", "low", "close"]
        complete_rows = 0
        for row in rows:
            if all(row.get(field) is not None for field in required_fields):
                complete_rows += 1

        data_completeness = (complete_rows / len(rows) * 100) if rows else 0
        if data_completeness < 95:
            raise ValueError(
                f"[SIGNAL_GENERATION_POOR_DATA_QUALITY] {symbol}: "
                f"Data completeness is {data_completeness:.0f}% ({complete_rows}/{len(rows)} rows have all OHLC fields). "
                f"Fail-fast: pivot detection requires >=95% complete OHLCV data for reliability (Minervini standard). "
                f"Incomplete data indicates upstream loader or data quality issue. "
                f"Verify: (1) price loader running successfully, (2) sufficient trading history, (3) database data integrity."
            )

        signals = []
        # Edge-trigger state, matching Pine's actual model (verified against user-provided
        # source 2026-08-19): the study section tracks an explicit in-position flag -
        # `inPosition := buy[1] ? true : sellSignal[1] ? false : inPosition[1]` - and only plots
        # `buyStudy = buy and flat` / `sellStudy = sellSignal and inPosition`. This is a real
        # position-state machine, NOT "did the raw condition merely change from yesterday": if
        # price re-breaks above an already-broken pivot while still in-position (no SELL fired
        # in between), Pine does NOT re-plot BUY - a same-bar-value comparison against the
        # previous bar's raw condition (this file's prior approach) would incorrectly re-fire in
        # that case. Likewise Pine never plots a bare SELL with no open position behind it.
        in_position = False

        for i, row in enumerate(rows):
            # Extract indicator values - explicit key checking (no silent .get() fallbacks)
            open_price = row["open"] if "open" in row else None
            high = row["high"] if "high" in row else None
            low = row["low"] if "low" in row else None
            close = row["close"] if "close" in row else None
            sma_50 = row["sma_50"] if "sma_50" in row else None
            sma_200 = row["sma_200"] if "sma_200" in row else None
            volume = row["volume"] if "volume" in row else None
            atr = row["atr"] if "atr" in row else None
            rsi = row["rsi"] if "rsi" in row else None
            macd = row["macd"] if "macd" in row else None
            macd_signal = row["macd_signal"] if "macd_signal" in row else None
            ema_21 = row["ema_21"] if "ema_21" in row else None
            adx = row["adx"] if "adx" in row else None
            mansfield_rs = row["mansfield_rs"] if "mansfield_rs" in row else None

            # Validate required OHLC fields - CRITICAL for signal generation
            if close is None or high is None or low is None:
                raise ValueError(
                    f"[SIGNAL GENERATION CRITICAL] {symbol} [{row.get('date')}]: "
                    f"Cannot generate signals without complete OHLC data. "
                    f"close={close}, high={high}, low={low}. "
                    f"Check that technical_data_daily loader populated all OHLC fields. "
                    f"Incomplete price data indicates upstream data loading failure."
                )

            # Phase 1: Find swing pivots. Only a *confirmed* pivot (strict 3-bar Pine-equivalent
            # pivothigh/pivotlow, no relaxed/fallback tiers) may trigger a signal - see
            # _find_confirmed_swing_high/_low docstrings for why. The relaxed multi-tier
            # _find_swing_low is used only as a stop-loss reference value when a BUY has
            # already triggered via a confirmed high but no confirmed low exists yet - Pine
            # itself doesn't need this (it just leaves stopLevel at na), but real position
            # sizing needs an actual numeric stop.
            confirmed_swing_high = self._find_confirmed_swing_high(rows, i)
            confirmed_swing_low = self._find_confirmed_swing_low(rows, i)
            stop_ref_swing_low = (
                confirmed_swing_low if confirmed_swing_low is not None else self._find_swing_low(symbol, rows, i)
            )

            # Phase 2: Generate signal from pivots (in-position state machine, matching Pine's
            # buyStudy/sellStudy exactly - see `in_position` comment above)
            signal_type, strength, reason, buylevel, stoplevel, raw_buy, raw_sell = self._generate_signal(
                symbol,
                close,
                high,
                low,
                sma_50,
                confirmed_swing_high,
                confirmed_swing_low,
                stop_ref_swing_low,
                in_position,
            )
            # Update state for the NEXT bar, mirroring Pine's `buy[1]`/`sellSignal[1]` lag:
            # this bar's raw condition (not this bar's edge-triggered signal_type) determines
            # whether the position is considered open starting next bar.
            if raw_buy:
                in_position = True
            elif raw_sell:
                in_position = False

            # Phase 3: Compute metrics if signal generated
            if signal_type:
                vol_surge, volume_surge_capped = self._compute_volume_surge(volume, rows, i)
                avg_vol_50d = None
                try:
                    avg_vol_50d = self._compute_avg_volume_50d(rows, i)
                except ValueError as e:
                    # Optional enrichment failed; log and continue with None value
                    logger.debug(f"[SIGNAL_GENERATION] {symbol} [{row.get('date')}]: {e!s}")
                    avg_vol_50d = None
                market_stage_result = self._determine_market_stage(close, sma_50, sma_200)

                # Handle market_stage result: could be string, dict (data unavailable), or None
                market_stage = None
                if isinstance(market_stage_result, dict) and market_stage_result.get("data_unavailable"):
                    # Data unavailable marker: leave market_stage as None
                    market_stage = None
                elif isinstance(market_stage_result, str):
                    market_stage = market_stage_result
                # else: market_stage remains None

                # Phase 4: Calculate entry/exit levels
                entry_exit = self._calculate_entry_exit_levels(signal_type, close, buylevel, stoplevel, atr)

                # Phase 5: Classify chart base pattern (BUY only - best-effort, never blocks signal generation)
                base_type_display, base_length_days = (
                    self._classify_base_type_safe(symbol, row["date"]) if signal_type == "BUY" else (None, None)
                )

                # Build signal record
                pct_from_sma50 = round((close - sma_50) / sma_50 * 100, 4) if sma_50 and close and sma_50 > 0 else None
                pct_from_ema21 = round((close - ema_21) / ema_21 * 100, 4) if ema_21 and close and ema_21 > 0 else None

                signal = {
                    "symbol": symbol,
                    "date": row["date"],
                    "signal_triggered_date": row["date"],
                    "timeframe": "1d",
                    "signal": signal_type,
                    "signal_type": signal_type,
                    "strength": float(strength),
                    "signal_strength": float(strength),
                    "reason": reason,
                    "entry_quality_score": None,
                    "signal_quality_score": None,
                    "volume_surge_pct": vol_surge,
                    "volume_surge_capped": volume_surge_capped,
                    "risk_reward_ratio": entry_exit["rr"],
                    "risk_pct": entry_exit["risk_pct"],
                    "rsi": float(rsi) if rsi is not None else None,
                    "sma_50": float(sma_50) if sma_50 is not None else None,
                    "sma_200": float(sma_200) if sma_200 is not None else None,
                    "ema_21": float(ema_21) if ema_21 is not None else None,
                    "pct_from_sma50": pct_from_sma50,
                    "pct_from_ema21": pct_from_ema21,
                    "atr": float(atr) if atr is not None else None,
                    "adx": float(adx) if adx is not None else None,
                    "mansfield_rs": (float(mansfield_rs) if mansfield_rs is not None else None),
                    "macd": float(macd) if macd is not None else None,
                    "macd_signal": (float(macd_signal) if macd_signal is not None else None),
                    "stage_number": None,
                    "market_stage": market_stage,
                    "base_type": base_type_display,
                    "base_length_days": base_length_days,
                    "open": float(open_price) if open_price is not None else None,
                    "high": float(high) if high is not None else None,
                    "low": float(low) if low is not None else None,
                    "close": float(close) if close is not None else None,
                    "volume": volume,
                    "avg_volume_50d": avg_vol_50d,
                    "buylevel": entry_exit["buylevel"],
                    "stoplevel": entry_exit["stoplevel"],
                    "initial_stop": entry_exit["initial_stop"],
                    "trailing_stop": entry_exit["trailing_stop"],
                    "sell_level": entry_exit["sell_level"],
                    "pivot_price": entry_exit["pivot_price"],
                    "buy_zone_start": entry_exit["buy_zone_start"],
                    "buy_zone_end": entry_exit["buy_zone_end"],
                    "profit_target_8pct": entry_exit["profit_target_8pct"],
                    "profit_target_20pct": entry_exit["profit_target_20pct"],
                    "profit_target_25pct": entry_exit["profit_target_25pct"],
                    "exit_trigger_1_price": entry_exit["exit_trigger_1"],
                    "exit_trigger_2_price": entry_exit["exit_trigger_2"],
                    "technical_data_age_days": tech_data_age,
                    "entry_price": float(close) if close is not None else None,
                }
                signals.append(signal)

        return signals

    def _find_confirmed_swing_high(self, rows: list[dict[str, Any]], i: int) -> float | None:
        """Find the most recent Pine-confirmed swing high (strict pivothigh(3,3), unbounded
        search) - the ONLY thing allowed to trigger a BUY. Deliberately does not fall back to
        the relaxed/no-history-yet tiers in _find_swing_high: those exist purely to give a
        real BUY a usable stop-loss reference when no confirmed low exists, not to invent a
        breakout level Pine wouldn't actually have. Letting a fallback tier trigger a signal
        was live-caught 2026-08-19: with the loader's real 120-day rolling fetch window, the
        first ~5 bars of EVERY symbol's window lack enough surrounding data for a confirmed
        pivot, so the old fallback (recent max within a small window) would trivially fire a
        spurious BUY there every run - which, under the correct in-position state machine
        (Pine only allows one open position at a time), then silently suppressed the real
        breakout signal for the rest of that symbol's 120-day window.
        """
        recent_swing_high = None
        for j in range(i):
            candidate = rows[j].get("high")
            if candidate is None:
                continue
            lookback_bars = [rows[k].get("high") for k in range(max(0, j - 3), j) if rows[k].get("high") is not None]
            # Bounded at i+1 (not len(rows)): rows extends through "today" even when scoring a
            # pivot for an earlier bar j, since the whole window is regenerated every run.
            # Without this bound, confirming bar j could use bars after evaluation bar i - data
            # that did not exist yet as of the date this signal is for.
            lookforward_bars = [
                rows[k].get("high")
                for k in range(j + 1, min(len(rows), i + 1, j + 4))
                if rows[k].get("high") is not None
            ]
            if len(lookback_bars) < 3 or len(lookforward_bars) < 3:
                continue
            if all(candidate > b for b in lookback_bars) and all(candidate > b for b in lookforward_bars):
                recent_swing_high = candidate  # most recent wins, matching Pine's valuewhen(...,0)
        return recent_swing_high

    def _find_confirmed_swing_low(self, rows: list[dict[str, Any]], i: int) -> float | None:
        """Find the most recent Pine-confirmed swing low (strict pivotlow(3,3), unbounded
        search) - the ONLY thing allowed to trigger a SELL. See _find_confirmed_swing_high
        docstring for why this must not fall back to relaxed tiers.
        """
        recent_swing_low = None
        for j in range(i):
            candidate = rows[j].get("low")
            if candidate is None:
                continue
            lookback_bars = [rows[k].get("low") for k in range(max(0, j - 3), j) if rows[k].get("low") is not None]
            lookforward_bars = [
                rows[k].get("low") for k in range(j + 1, min(len(rows), i + 1, j + 4)) if rows[k].get("low") is not None
            ]
            if len(lookback_bars) < 3 or len(lookforward_bars) < 3:
                continue
            if all(candidate < b for b in lookback_bars) and all(candidate < b for b in lookforward_bars):
                recent_swing_low = candidate  # most recent wins, matching Pine's valuewhen(...,0)
        return recent_swing_low

    def _find_swing_high(self, symbol: str, rows: list[dict[str, Any]], i: int) -> float | None:
        """Find the most recent confirmed swing high, matching Pine's `pivothigh(high, 3, 3)`
        + `valuewhen(...)` exactly: a 3-bar-left/3-bar-right confirmed pivot, searched back
        through ALL available history (no fixed lookback window - Pine's valuewhen never
        expires a level, it persists until a newer pivot replaces it).

        Strategy 1: Perfect swing (high > all surrounding bars in 3-bar window) - the real Pine
            pivothigh condition.
        Strategy 2: Relative swing (high > most surrounding bars, allow 1 exception) - not part
            of Pine; leniency for real-world data gaps.
        Strategy 3: Recent maximum in a bounded window - last-resort fallback, also not part of
            Pine; only reached when strategies 1/2 find nothing at all (e.g. insufficient
            history for a 3-bar confirmation).
        """
        recent_swing_high = None

        # STRATEGY 1: Perfect swing (Pine's actual pivothigh(3,3) condition) - unbounded search
        for j in range(i):
            candidate = rows[j].get("high")
            if candidate is None:
                continue

            # Collect nearby bars (may have gaps)
            lookback_bars = [rows[k].get("high") for k in range(max(0, j - 3), j) if rows[k].get("high") is not None]
            # Bounded at i+1 (not len(rows)): rows extends through "today" even when
            # scoring a pivot for an earlier bar j, since the whole lookback window is
            # regenerated every run. Without this bound, confirming bar j as a pivot
            # could use bars after evaluation bar i - data that did not exist yet as of
            # the date this signal is for.
            lookforward_bars = [
                rows[k].get("high")
                for k in range(j + 1, min(len(rows), i + 1, j + 4))
                if rows[k].get("high") is not None
            ]

            if len(lookback_bars) < 2 or len(lookforward_bars) < 2:
                continue

            # Validate pivot: candidate must be higher than all available lookback and lookforward bars.
            # Take the MOST RECENT confirmed pivot (largest j), matching Pine's valuewhen(..., 0)
            # semantics - not the highest price seen, which would deviate from "most recent".
            if all(candidate > b for b in lookback_bars) and all(candidate > b for b in lookforward_bars):
                recent_swing_high = candidate

        if recent_swing_high is not None:
            return float(recent_swing_high)

        # STRATEGY 2: Relative swing (high > most surrounding bars, allow 1 exception) - unbounded
        for j in range(i):
            candidate = rows[j].get("high")
            if candidate is None:
                continue

            lookback_bars = [rows[k].get("high") for k in range(max(0, j - 3), j) if rows[k].get("high") is not None]
            lookforward_bars = [
                rows[k].get("high")
                for k in range(j + 1, min(len(rows), i + 1, j + 4))
                if rows[k].get("high") is not None
            ]

            if len(lookback_bars) < 1 or len(lookforward_bars) < 1:
                continue

            # Relative swing: candidate is higher than majority (allow 1 exception)
            lookback_higher = sum(1 for b in lookback_bars if candidate > b)
            lookforward_higher = sum(1 for b in lookforward_bars if candidate > b)
            if lookback_higher >= len(lookback_bars) - 1 and lookforward_higher >= len(lookforward_bars) - 1:
                recent_swing_high = candidate

        if recent_swing_high is not None:
            return float(recent_swing_high)

        # STRATEGY 3: Recent maximum in a bounded window - last resort, not part of Pine
        max_price = None
        for j in range(max(0, i - SWING_HIGH_LOOKBACK_BARS), i):
            high = rows[j].get("high")
            if high is not None and (max_price is None or high > max_price):
                max_price = high
        return max_price

    def _find_swing_low(self, symbol: str, rows: list[dict[str, Any]], i: int) -> float | None:
        """Find the most recent confirmed swing low, matching Pine's `pivotlow(low, 3, 3)`
        + `valuewhen(...)` exactly - see `_find_swing_high` docstring for the full rationale
        (unbounded search, most-recent-not-lowest tie-breaking).
        """
        recent_swing_low = None

        # STRATEGY 1: Perfect swing (Pine's actual pivotlow(3,3) condition) - unbounded search
        for j in range(i):
            candidate = rows[j].get("low")
            if candidate is None:
                continue

            # Collect nearby bars (may have gaps)
            lookback_bars = [rows[k].get("low") for k in range(max(0, j - 3), j) if rows[k].get("low") is not None]
            # Bounded at i+1, not len(rows) - see matching comment in _find_swing_high.
            lookforward_bars = [
                rows[k].get("low") for k in range(j + 1, min(len(rows), i + 1, j + 4)) if rows[k].get("low") is not None
            ]

            if len(lookback_bars) < 2 or len(lookforward_bars) < 2:
                continue

            # Validate pivot: candidate must be lower than all available lookback and lookforward
            # bars. Take the MOST RECENT confirmed pivot (largest j), matching Pine's
            # valuewhen(..., 0) semantics - not the lowest price seen.
            if all(candidate < b for b in lookback_bars) and all(candidate < b for b in lookforward_bars):
                recent_swing_low = candidate

        if recent_swing_low is not None:
            return float(recent_swing_low)

        # STRATEGY 2: Relative swing (low < most surrounding bars, allow 1 exception) - unbounded.
        # This handles choppy markets where perfect swings are rare. Not part of Pine.
        for j in range(i):
            candidate = rows[j].get("low")
            if candidate is None:
                continue

            lookback_bars = [rows[k].get("low") for k in range(max(0, j - 3), j) if rows[k].get("low") is not None]
            lookforward_bars = [
                rows[k].get("low") for k in range(j + 1, min(len(rows), i + 1, j + 4)) if rows[k].get("low") is not None
            ]

            if len(lookback_bars) < 1 or len(lookforward_bars) < 1:
                continue

            # Relative swing: candidate is lower than majority (allow 1 exception)
            lookback_lower = sum(1 for b in lookback_bars if candidate < b)
            lookforward_lower = sum(1 for b in lookforward_bars if candidate < b)
            if lookback_lower >= len(lookback_bars) - 1 and lookforward_lower >= len(lookforward_bars) - 1:
                recent_swing_low = candidate

        if recent_swing_low is not None:
            return float(recent_swing_low)

        # STRATEGY 3: Recent minimum in a bounded window - last resort, not part of Pine
        min_price = None
        for j in range(max(0, i - SWING_LOW_LOOKBACK_BARS), i):
            low = rows[j].get("low")
            if low is not None and (min_price is None or low < min_price):
                min_price = low
        return min_price

    def _generate_signal(
        self,
        symbol: str,
        close: float,
        high: float,
        low: float,
        sma_50: float | None,
        confirmed_swing_high: float | None,
        confirmed_swing_low: float | None,
        stop_ref_swing_low: float | None,
        in_position: bool,
    ) -> tuple[str | None, float, str, float | None, float | None, bool, bool]:
        """Generate BUY/SELL signal from swing pivots, matching Pine exactly:

            buySignal = high > buyLevel
            buy = buySignal and buyLevel > maFilter   (maFilter = sma(close, 50) on THIS bar)
            sellSignal = low < stopLevel
            buyStudy = buy and flat        (flat = not in_position)
            sellStudy = sellSignal and inPosition

        signal_type is only set when the in-position state machine says to (BUY only while
        flat, SELL only while in a position) - not merely "condition changed since last bar".
        The two returned booleans are the raw (non-edge-triggered) buy/sell condition for this
        bar, which the caller uses to update in_position for the next bar. confirmed_swing_high/
        low must come from a strict Pine-equivalent pivot (see _find_confirmed_swing_high/_low)
        - only that may trigger a signal. stop_ref_swing_low may come from a relaxed fallback
        tier and is used only as the BUY's numeric stop-loss value, never to decide triggering.
        """
        signal_type = None
        strength = 0.0
        reason = ""
        buylevel = None
        stoplevel = None

        # MA filter compares the swing high against THIS bar's SMA50 (Pine's `maFilter` is a
        # plain series evaluated at the current bar), not the SMA50 at the time the pivot formed.
        raw_buy = bool(
            confirmed_swing_high and sma_50 and high > confirmed_swing_high and confirmed_swing_high > sma_50
        )
        raw_sell = bool(confirmed_swing_low and low < confirmed_swing_low)

        buy_active = raw_buy and not in_position
        sell_active = raw_sell and in_position

        # BUY: Breakout above swing high where swing_high > current SMA50, only while flat
        if buy_active:
            signal_type = "BUY"
            # raw_buy's definition guarantees both are non-None (mypy can't narrow through
            # the bool() wrapper the way it could narrow the old inline condition directly).
            assert confirmed_swing_high is not None and sma_50 is not None
            if confirmed_swing_high <= 0:
                raise RuntimeError(
                    f"[SIGNAL_GENERATION] Invalid confirmed_swing_high={confirmed_swing_high} for {symbol}: "
                    "swing high must be positive for BUY signal calculation."
                )
            breakout_pct = (high - confirmed_swing_high) / confirmed_swing_high * 100
            strength = min(0.5 + (breakout_pct / 5.0), 1.0)
            reason = f"Breakout above swing high ({abs(breakout_pct):.1f}%) with price > SMA50"
            # BUG FOUND 2026-08-10: bare round() on a float, the same binary-representation
            # risk this file's own SELL branch below (~line 432) was already fixed for and
            # explicitly cites as "already fixed 2026-07-21 in order_manager.py,
            # exposure_policy.py, and position_monitor.py" - just never applied here, in the
            # branch that actually feeds real BUY trades (SELL signals aren't consumed by
            # real entry execution - see phase7_signal_generation.py's `signal = 'BUY'`
            # filter). buylevel/stoplevel here become _calculate_entry_exit_levels()'s
            # Decimal(str(buylevel)) input, baking in any float-rounding drift permanently.
            buylevel = float(Decimal(str(confirmed_swing_high)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))
            if not stop_ref_swing_low:
                raise RuntimeError(
                    f"[SIGNAL_GENERATION_CRITICAL] {symbol}: BUY signal detected but cannot calculate stop loss. "
                    f"No swing_low pivot found (confirmed or fallback). "
                    f"Fail-fast: cannot proceed without risk level definition. "
                    f"Incomplete signal generation indicates data quality or pivot detection issue. "
                    f"Verify: (1) sufficient price history, (2) data completeness, (3) pivot detection logic."
                )
            stoplevel = float(Decimal(str(stop_ref_swing_low)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))

        # SELL: Breakdown below swing low (stop loss), only while in a position
        elif sell_active:
            signal_type = "SELL"
            # sell_active's definition guarantees this is non-None (see BUY-branch comment above).
            assert confirmed_swing_low is not None
            if confirmed_swing_low <= 0:
                raise RuntimeError(
                    f"[SIGNAL_GENERATION] Invalid confirmed_swing_low={confirmed_swing_low} for {symbol}: "
                    "swing low must be positive for SELL signal calculation."
                )
            breakdown_pct = (confirmed_swing_low - low) / confirmed_swing_low * 100
            strength = min(0.5 + (breakdown_pct / 5.0), 1.0)
            reason = f"Breakdown below swing low ({abs(breakdown_pct):.1f}%)"
            # Same bare-round() inconsistency as the BUY branch's buylevel/stoplevel above -
            # this one line was missed when stoplevel just below got the Decimal fix.
            buylevel = float(Decimal(str(close)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))
            # Decimal, not round(close * 1.08, 4): close * 1.08 is float multiplication -
            # same binary-representation risk already fixed 2026-07-21 in order_manager.py,
            # exposure_policy.py, and position_monitor.py. This stoplevel is the actual stop
            # loss written to buy_sell_daily/algo_trades and feeds real position sizing.
            stoplevel = float(
                (Decimal(str(close)) * Decimal("1.08")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            )

        return signal_type, strength, reason, buylevel, stoplevel, raw_buy, raw_sell

    def _compute_volume_surge(
        self, volume: float | None, rows: list[dict[str, Any]], i: int
    ) -> tuple[float | None, bool]:
        vol_surge = None
        volume_surge_capped = False
        decimal84_max = 9999.9999

        if volume is not None and i >= 5:
            recent_vols: list[Any] = [
                rows[j].get("volume") for j in range(max(0, i - 20), i) if rows[j].get("volume") is not None
            ]
            if recent_vols:
                avg_vol = sum(recent_vols) / len(recent_vols)
                if avg_vol > 0:
                    raw_surge = (volume / avg_vol - 1) * 100
                    if raw_surge > decimal84_max:
                        volume_surge_capped = True
                    vol_surge = round(min(raw_surge, decimal84_max), 2)

        return vol_surge, volume_surge_capped

    def _compute_avg_volume_50d(self, rows: list[dict[str, Any]], i: int) -> int:
        """Compute 50-bar average volume.

        Returns int if sufficient historical data available.
        Raises ValueError if insufficient history (explicit fail-fast for data quality).

        Args:
            rows: List of technical data rows
            i: Current bar index (position in rows)

        Returns:
            50-bar average volume as integer

        Raises:
            ValueError: If insufficient history (< 10 bars or insufficient volume data)
        """
        if i < 10:
            raise ValueError(
                f"[SIGNAL_METRICS] Cannot compute 50d volume average: insufficient history. "
                f"Current bar index {i}, but require >= 10 bars for meaningful average. "
                f"Fail-fast: enrichment requires minimum data depth. Early bars cannot be reliably scored."
            )

        vols_50: list[Any] = [
            rows[j].get("volume") for j in range(max(0, i - 50), i) if rows[j].get("volume") is not None
        ]
        if not vols_50:
            raise ValueError(
                f"[SIGNAL_METRICS] Cannot compute 50d volume average: no volume data in 50-bar window. "
                f"Bar index {i}, searched {i - max(0, i - 50)} bars. "
                f"Fail-fast: volume data missing - data quality issue in technical data loader."
            )

        return int(sum(vols_50) / len(vols_50))

    def _determine_market_stage(
        self, close: float, sma_50: float | None, sma_200: float | None
    ) -> str | dict[str, Any] | None:
        """Determine market stage from moving average positions.

        Returns:
            str: Stage name ("Stage 1", "Stage 2", "Stage 3", "Stage 4") if determinable
            dict: With data_unavailable marker if data missing
                {"data_unavailable": True, "reason": str}
            None: If SMA relationship doesn't fit any stage

        Per CLAUDE.md governance: Optional enrichment must return explicit data_unavailable
        markers instead of silently returning None, enabling visibility into data failures.
        """
        if close and sma_50 and sma_200:
            if close > sma_50 > sma_200:
                return "Stage 2"
            elif close > sma_200 and close < sma_50:
                return "Stage 1"
            elif close < sma_50 < sma_200:
                return "Stage 4"
            elif close < sma_200 and close > sma_50:
                return "Stage 3"
            # Remaining two orderings are "crossing" states where price has already moved past
            # sma_200 but sma_50 hasn't caught up yet (or vice versa) - the MAs haven't confirmed
            # the new stage. Classify by the still-forming stage rather than reporting the
            # complete close/sma_50/sma_200 data as unusable.
            elif close > sma_200 > sma_50:
                # Price reclaimed the long-term average ahead of the 50d MA - early recovery,
                # not yet a confirmed Stage 2 uptrend (50d MA still below the 200d MA).
                return "Stage 1"
            elif sma_50 > sma_200 > close:
                # Price broke below both averages ahead of the 50d MA rolling over - breakdown
                # starting, not yet a confirmed Stage 4 downtrend (50d MA still above the 200d MA).
                return "Stage 3"
            reason = f"ambiguous_sma_relationship (close={close}, sma_50={sma_50}, sma_200={sma_200})"
            logger.debug(f"[SIGNAL_METRICS] Market stage cannot be determined from SMA relationship - {reason}")
            return {"data_unavailable": True, "reason": reason}
        else:
            missing = []
            if not close:
                missing.append("close")
            if sma_50 is None:
                missing.append("sma_50")
            if sma_200 is None:
                missing.append("sma_200")
            reason = f"missing_fields: {', '.join(missing)}"
            logger.debug(f"[SIGNAL_METRICS] Cannot determine market stage - {reason}")
            return {"data_unavailable": True, "reason": reason}

    def _classify_base_type_safe(self, symbol: str, eval_date: Any) -> tuple[str | None, int | None]:
        """Classify the chart base pattern for a BUY candidate (best-effort).

        Uses algo/signals/signal_patterns.py::classify_base_type via SignalComputer. This
        analysis has no bearing on whether a signal fires (pivot-breakout logic already decided
        that) and must never block or fail signal generation - any error here is caught and
        logged, returning (None, None) so the candidate is still emitted without pattern data.
        """
        try:
            if self._pattern_classifier is None:
                from algo.signals.signal_computer import SignalComputer

                self._pattern_classifier = SignalComputer(config={})

            classification = self._pattern_classifier.classify_base_type(symbol, eval_date)
            if not classification or classification.get("data_unavailable"):
                return None, None

            pattern_type = classification.get("type")
            if pattern_type is None or pattern_type in ("no_base",):
                return None, None

            display_name = _BASE_TYPE_DISPLAY.get(pattern_type, pattern_type.replace("_", " ").title())
            duration_weeks = classification.get("duration_weeks")
            base_length_days = int(duration_weeks * 5) if duration_weeks is not None else None
            return display_name, base_length_days
        except Exception as e:  # best-effort enrichment, must never break signal generation
            logger.warning(
                f"[SIGNAL_GENERATION] {symbol}: base pattern classification failed - {type(e).__name__}: {e}"
            )
            return None, None

    def _calculate_entry_exit_levels(
        self,
        signal_type: str,
        close: float,
        buylevel: Decimal | float | None,
        stoplevel: Decimal | float | None,
        atr: float | None,
    ) -> dict[str, Any]:
        """Calculate entry/exit levels and risk/reward metrics."""
        result: dict[str, Any] = {
            "buylevel": buylevel,
            "stoplevel": stoplevel,
            "initial_stop": None,
            "trailing_stop": None,
            "sell_level": None,
            "pivot_price": None,
            "buy_zone_start": None,
            "buy_zone_end": None,
            "profit_target_8pct": None,
            "profit_target_20pct": None,
            "profit_target_25pct": None,
            "exit_trigger_1": None,
            "exit_trigger_2": None,
            "rr": None,
            # CRITICAL: must reflect THIS candidate's actual entry-to-stop distance (same
            # buy_dec/stop_dec used for `rr` below) - used to be a hardcoded 8.0 regardless of the
            # real stop distance (confirmed live: 41,768/41,768 buy_sell_daily rows had the
            # identical value). None here (not a fake default) unless a BUY/SELL branch below sets
            # a real value, consistent with the rest of this dict using None for unset fields.
            "risk_pct": None,
        }

        if signal_type == "BUY" and close:
            if buylevel is None:
                raise ValueError(
                    "[SIGNAL_GENERATION_CRITICAL] BUY signal generated but buylevel is None. "
                    "Signal generation logic failed to set entry price from swing pivot. "
                    "Cannot proceed with trade entry without valid entry level. "
                    "Check _generate_signal() logic for swing high detection."
                )
            if stoplevel is None:
                raise ValueError(
                    "[SIGNAL_GENERATION_CRITICAL] BUY signal generated but stoplevel is None. "
                    "Signal generation logic failed to set stop loss from swing pivot. "
                    "Cannot proceed without valid risk level. "
                    "Check _generate_signal() logic for swing low detection."
                )
            # CRITICAL: Require ATR for volatility-adjusted profit targets (fail-fast if missing)
            if atr is None or atr <= 0:
                raise ValueError(
                    f"[SIGNAL_GENERATION_CRITICAL] Cannot calculate profit targets without ATR data. "
                    f"ATR is required for volatility-adjusted exits (stocks vary: low-vol 2-3%, high-vol 8-15%). "
                    f"Profit targets must adapt to market volatility - fixed percentages are unreliable. "
                    f"ATR={atr}. Verify technical_data_daily loader populated atr field."
                )

            buy_dec = Decimal(str(buylevel))
            stop_dec = Decimal(str(stoplevel))
            atr_dec = Decimal(str(atr))

            result["buylevel"] = buy_dec
            result["stoplevel"] = stop_dec
            result["initial_stop"] = stop_dec
            result["trailing_stop"] = stop_dec
            result["sell_level"] = stop_dec
            result["pivot_price"] = buy_dec
            result["buy_zone_start"] = (buy_dec * Decimal("0.99")).quantize(Decimal("0.0001"))
            result["buy_zone_end"] = (buy_dec * Decimal("1.05")).quantize(Decimal("0.0001"))
            # Profit targets scaled by ATR: conservative (1.5x), moderate (3x), aggressive (4.5x)
            result["profit_target_8pct"] = (buy_dec + atr_dec * Decimal("1.5")).quantize(Decimal("0.0001"))
            result["profit_target_20pct"] = (buy_dec + atr_dec * Decimal("3.0")).quantize(Decimal("0.0001"))
            result["profit_target_25pct"] = (buy_dec + atr_dec * Decimal("4.5")).quantize(Decimal("0.0001"))
            result["exit_trigger_1"] = result["profit_target_8pct"]
            result["exit_trigger_2"] = result["profit_target_20pct"]
            result["rr"] = (
                (result["profit_target_20pct"] - buy_dec) / max(buy_dec - stop_dec, Decimal("0.01"))
            ).quantize(Decimal("0.01"))
            result["risk_pct"] = float(((buy_dec - stop_dec) / buy_dec * 100).quantize(Decimal("0.01")))

        elif signal_type == "SELL" and close:
            if buylevel is None:
                raise ValueError(
                    "[SIGNAL_GENERATION_CRITICAL] SELL signal generated but buylevel is None. "
                    "Signal generation logic failed to set reference price. "
                    "Cannot proceed with short entry without valid reference level. "
                    "Check _generate_signal() logic."
                )
            if stoplevel is None:
                raise ValueError(
                    "[SIGNAL_GENERATION_CRITICAL] SELL signal generated but stoplevel is None. "
                    "Signal generation logic failed to set stop loss for short. "
                    "Cannot proceed without valid risk level. "
                    "Check _generate_signal() logic."
                )
            # CRITICAL: Require ATR for volatility-adjusted profit targets (fail-fast if missing)
            if atr is None or atr <= 0:
                raise ValueError(
                    f"[SIGNAL_GENERATION_CRITICAL] Cannot calculate profit targets without ATR data. "
                    f"ATR is required for volatility-adjusted exits (stocks vary: low-vol 2-3%, high-vol 8-15%). "
                    f"Profit targets must adapt to market volatility - fixed percentages are unreliable. "
                    f"ATR={atr}. Verify technical_data_daily loader populated atr field."
                )

            buy_dec = Decimal(str(buylevel))
            stop_dec = Decimal(str(stoplevel))
            atr_dec = Decimal(str(atr))

            result["buylevel"] = buy_dec
            result["stoplevel"] = stop_dec
            result["initial_stop"] = stop_dec
            result["trailing_stop"] = stop_dec
            result["sell_level"] = Decimal(str(close)).quantize(Decimal("0.0001"))
            result["pivot_price"] = buy_dec
            # Profit targets (downside for shorts) scaled by ATR: conservative (1.5x), moderate (3x), aggressive (4.5x)
            result["profit_target_8pct"] = (buy_dec - atr_dec * Decimal("1.5")).quantize(Decimal("0.0001"))
            result["profit_target_20pct"] = (buy_dec - atr_dec * Decimal("3.0")).quantize(Decimal("0.0001"))
            result["profit_target_25pct"] = (buy_dec - atr_dec * Decimal("4.5")).quantize(Decimal("0.0001"))
            result["exit_trigger_1"] = result["profit_target_8pct"]
            result["exit_trigger_2"] = result["profit_target_20pct"]
            result["rr"] = (
                (buy_dec - result["profit_target_20pct"]) / max(stop_dec - buy_dec, Decimal("0.01"))
            ).quantize(Decimal("0.01"))
            result["risk_pct"] = float(((stop_dec - buy_dec) / buy_dec * 100).quantize(Decimal("0.01")))

        return result
