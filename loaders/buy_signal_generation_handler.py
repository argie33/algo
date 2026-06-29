#!/usr/bin/env python3
"""Buy/sell signal generation handler extracted from SignalsDailyLoader.

Handles:
- Swing pivot detection (highs and lows)
- Signal generation logic (BUY/SELL triggers)
- Volume metrics and market stage computation
- Entry/exit level calculation
"""

import logging
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


class BuySignalGenerationHandler:
    """Handles buy/sell signal generation from technical indicator rows."""

    def __init__(self, loader: Any) -> None:
        """Initialize with reference to SignalsDailyLoader."""
        self.loader = loader

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
        """
        if not rows:
            raise RuntimeError(
                f"[SIGNAL_GENERATION_MISSING_DATA] Cannot generate buy/sell signals for {symbol}: "
                f"technical data unavailable. Signal generation requires OHLCV and indicator values."
            )
        signals = []

        for i, row in enumerate(rows):
            # Extract indicator values
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

            # Validate required OHLC fields - CRITICAL for signal generation
            if close is None or high is None or low is None:
                raise ValueError(
                    f"[SIGNAL GENERATION CRITICAL] {symbol} [{row.get('date')}]: "
                    f"Cannot generate signals without complete OHLC data. "
                    f"close={close}, high={high}, low={low}. "
                    f"Check that technical_data_daily loader populated all OHLC fields. "
                    f"Incomplete price data indicates upstream data loading failure."
                )

            # Phase 1: Find swing pivots
            recent_swing_high, swing_high_sma50 = self._find_swing_high(symbol, rows, i)
            recent_swing_low = self._find_swing_low(symbol, rows, i)

            # Phase 2: Generate signal from pivots
            signal_type, strength, reason, buylevel, stoplevel = self._generate_signal(
                symbol,
                close,
                high,
                low,
                recent_swing_high,
                swing_high_sma50,
                recent_swing_low,
            )

            # Phase 3: Compute metrics if signal generated
            if signal_type:
                vol_surge, volume_surge_capped = self._compute_volume_surge(volume, rows, i)
                avg_vol_50d = self._compute_avg_volume_50d(rows, i)
                market_stage = self._determine_market_stage(close, sma_50, sma_200)

                # Phase 4: Calculate entry/exit levels
                entry_exit = self._calculate_entry_exit_levels(signal_type, close, buylevel, stoplevel)

                # Build signal record
                signal = {
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
                    "risk_reward_ratio": entry_exit["rr"],
                    "risk_pct": entry_exit["risk_pct"],
                    "rsi": float(rsi) if rsi is not None else None,
                    "sma_50": float(sma_50) if sma_50 is not None else None,
                    "sma_200": float(sma_200) if sma_200 is not None else None,
                    "ema_21": float(ema_21) if ema_21 is not None else None,
                    "atr": float(atr) if atr is not None else None,
                    "adx": float(adx) if adx is not None else None,
                    "mansfield_rs": (float(mansfield_rs) if mansfield_rs is not None else None),
                    "macd": float(macd) if macd is not None else None,
                    "macd_signal": (float(macd_signal) if macd_signal is not None else None),
                    "stage_number": None,
                    "market_stage": market_stage,
                    "open": row.get("open"),
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
                }
                signals.append(signal)

        return signals

    def _find_swing_high(self, symbol: str, rows: list[dict[str, Any]], i: int) -> tuple[float | None, float | None]:
        """Find most recent swing high using extended 50-bar lookback with lenient data requirements.

        ISSUE FIX: Increased from 20-bar to 50-bar lookback to detect pivots that occurred
        further back. Made data completeness lenient to work with real-world incomplete data
        while maintaining pivot integrity.
        """
        recent_swing_high = None
        swing_high_sma50 = None

        for j in range(max(0, i - 50), i):
            candidate = rows[j].get("high")
            if not candidate:
                continue

            # Collect nearby bars (may have gaps)
            lookback_bars = [rows[k].get("high") for k in range(max(0, j - 3), j) if rows[k].get("high")]
            lookforward_bars = [rows[k].get("high") for k in range(j + 1, min(len(rows), j + 4)) if rows[k].get("high")]

            # Lenient requirement: need at least 2 lookback and 2 lookforward bars (was requiring all)
            if len(lookback_bars) < 2 or len(lookforward_bars) < 2:
                continue

            # Validate pivot: candidate must be higher than all available lookback and lookforward bars
            if all(candidate > b for b in lookback_bars) and all(candidate > b for b in lookforward_bars):
                if recent_swing_high is None or candidate > recent_swing_high:
                    recent_swing_high = candidate
                    swing_high_sma50 = rows[j].get("sma_50")

        return recent_swing_high, swing_high_sma50

    def _find_swing_low(self, symbol: str, rows: list[dict[str, Any]], i: int) -> float | None:
        """Find most recent swing low using extended 50-bar lookback with lenient data requirements.

        ISSUE FIX: Increased from 10-bar to 50-bar lookback to detect stop loss levels
        further back. Made data completeness lenient to work with real-world incomplete data
        while maintaining pivot integrity.
        """
        recent_swing_low = None

        for j in range(max(0, i - 50), i):
            candidate = rows[j].get("low")
            if not candidate:
                continue

            # Collect nearby bars (may have gaps)
            lookback_bars = [rows[k].get("low") for k in range(max(0, j - 3), j) if rows[k].get("low")]
            lookforward_bars = [rows[k].get("low") for k in range(j + 1, min(len(rows), j + 4)) if rows[k].get("low")]

            # Lenient requirement: need at least 2 lookback and 2 lookforward bars (was requiring all)
            if len(lookback_bars) < 2 or len(lookforward_bars) < 2:
                continue

            # Validate pivot: candidate must be lower than all available lookback and lookforward bars
            if all(candidate < b for b in lookback_bars) and all(candidate < b for b in lookforward_bars):
                if recent_swing_low is None or candidate < recent_swing_low:
                    recent_swing_low = candidate

        return recent_swing_low

    def _generate_signal(
        self,
        symbol: str,
        close: float,
        high: float,
        low: float,
        recent_swing_high: float | None,
        swing_high_sma50: float | None,
        recent_swing_low: float | None,
    ) -> tuple[str | None, float, str, float | None, float | None]:
        """Generate BUY/SELL signal from swing pivots."""
        signal_type = None
        strength = 0.0
        reason = ""
        buylevel = None
        stoplevel = None

        # BUY: Breakout above swing high where swing_high > SMA50
        if recent_swing_high and swing_high_sma50 and high > recent_swing_high and recent_swing_high > swing_high_sma50:
            signal_type = "BUY"
            if recent_swing_high <= 0:
                raise RuntimeError(
                    f"[SIGNAL_GENERATION] Invalid recent_swing_high={recent_swing_high} for {symbol}: "
                    "swing high must be positive for BUY signal calculation."
                )
            breakout_pct = (high - recent_swing_high) / recent_swing_high * 100
            strength = min(0.5 + (breakout_pct / 5.0), 1.0)
            reason = f"Breakout above swing high ({abs(breakout_pct):.1f}%) with price > SMA50"
            buylevel = round(recent_swing_high, 4)
            if not recent_swing_low:
                raise RuntimeError(
                    f"[SIGNAL_GENERATION] {symbol}: BUY signal requires recent_swing_low for stop loss calculation. "
                    "Cannot generate signal without technical pivot data."
                )
            stoplevel = round(recent_swing_low, 4)

        # SELL: Breakdown below swing low (stop loss)
        elif recent_swing_low and low < recent_swing_low:
            signal_type = "SELL"
            if recent_swing_low <= 0:
                raise RuntimeError(
                    f"[SIGNAL_GENERATION] Invalid recent_swing_low={recent_swing_low} for {symbol}: "
                    "swing low must be positive for SELL signal calculation."
                )
            breakdown_pct = (recent_swing_low - low) / recent_swing_low * 100
            strength = min(0.5 + (breakdown_pct / 5.0), 1.0)
            reason = f"Breakdown below swing low ({abs(breakdown_pct):.1f}%)"
            buylevel = round(close, 4)
            stoplevel = round(close * 1.08, 4)

        return signal_type, strength, reason, buylevel, stoplevel

    def _compute_volume_surge(
        self, volume: float | None, rows: list[dict[str, Any]], i: int
    ) -> tuple[float | None, bool]:
        """Compute volume surge: compare to 20-bar average volume."""
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

    def _compute_avg_volume_50d(self, rows: list[dict[str, Any]], i: int) -> int | None:
        """Compute 50-bar average volume."""
        if i >= 10:
            vols_50: list[Any] = [
                rows[j].get("volume") for j in range(max(0, i - 50), i) if rows[j].get("volume") is not None
            ]
            if vols_50:
                return int(sum(vols_50) / len(vols_50))
            logger.debug(f"[SIGNAL_METRICS] Insufficient volume data to compute 50d average (bar index {i})")
        else:
            logger.debug(f"[SIGNAL_METRICS] Insufficient history for 50d average (only {i} bars available, need >= 10)")
        return None

    def _determine_market_stage(self, close: float, sma_50: float | None, sma_200: float | None) -> str | None:
        """Determine market stage from moving average positions."""
        if close and sma_50 and sma_200:
            if close > sma_50 > sma_200:
                return "Stage 2"
            elif close > sma_200 and close < sma_50:
                return "Stage 1"
            elif close < sma_50 < sma_200:
                return "Stage 4"
            elif close < sma_200 and close > sma_50:
                return "Stage 3"
            logger.debug(f"[SIGNAL_METRICS] Market stage cannot be determined from SMA relationship (close={close}, sma_50={sma_50}, sma_200={sma_200})")
        else:
            missing = []
            if not close:
                missing.append("close")
            if sma_50 is None:
                missing.append("sma_50")
            if sma_200 is None:
                missing.append("sma_200")
            logger.debug(f"[SIGNAL_METRICS] Cannot determine market stage - missing: {', '.join(missing)}")
        return None

    def _calculate_entry_exit_levels(
        self,
        signal_type: str,
        close: float,
        buylevel: Decimal | float | None,
        stoplevel: Decimal | float | None,
    ) -> dict[str, Any]:
        """Calculate entry/exit levels and risk/reward metrics."""
        risk_pct = 8.0
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
            "risk_pct": risk_pct,
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
            buy_dec = Decimal(str(buylevel))
            stop_dec = Decimal(str(stoplevel))

            result["buylevel"] = buy_dec
            result["stoplevel"] = stop_dec
            result["initial_stop"] = stop_dec
            result["trailing_stop"] = stop_dec
            result["sell_level"] = stop_dec
            result["pivot_price"] = buy_dec
            result["buy_zone_start"] = (buy_dec * Decimal("0.99")).quantize(Decimal("0.0001"))
            result["buy_zone_end"] = (buy_dec * Decimal("1.05")).quantize(Decimal("0.0001"))
            result["profit_target_8pct"] = (buy_dec * Decimal("1.08")).quantize(Decimal("0.0001"))
            result["profit_target_20pct"] = (buy_dec * Decimal("1.20")).quantize(Decimal("0.0001"))
            result["profit_target_25pct"] = (buy_dec * Decimal("1.25")).quantize(Decimal("0.0001"))
            result["exit_trigger_1"] = result["profit_target_8pct"]
            result["exit_trigger_2"] = result["profit_target_20pct"]
            result["rr"] = (
                (result["profit_target_20pct"] - buy_dec) / max(buy_dec - stop_dec, Decimal("0.01"))
            ).quantize(Decimal("0.01"))

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
            buy_dec = Decimal(str(buylevel))
            stop_dec = Decimal(str(stoplevel))

            result["buylevel"] = buy_dec
            result["stoplevel"] = stop_dec
            result["initial_stop"] = stop_dec
            result["trailing_stop"] = stop_dec
            result["sell_level"] = Decimal(str(close)).quantize(Decimal("0.0001"))
            result["pivot_price"] = buy_dec
            result["profit_target_8pct"] = (buy_dec * Decimal("0.92")).quantize(Decimal("0.0001"))
            result["profit_target_20pct"] = (buy_dec * Decimal("0.80")).quantize(Decimal("0.0001"))
            result["profit_target_25pct"] = (buy_dec * Decimal("0.75")).quantize(Decimal("0.0001"))
            result["exit_trigger_1"] = result["profit_target_8pct"]
            result["exit_trigger_2"] = result["profit_target_20pct"]
            result["rr"] = (
                (buy_dec - result["profit_target_20pct"]) / max(stop_dec - buy_dec, Decimal("0.01"))
            ).quantize(Decimal("0.01"))

        return result
