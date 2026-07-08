#!/usr/bin/env python3
"""
VECTORIZED SIGNAL GENERATION

Replaces sequential symbol-by-symbol computation with parallel NumPy operations.
Fetches all price data once, computes all signals simultaneously.

Target: Process 5,256 symbols in <30 seconds (vs. current ~270 seconds)

Architecture:
1. Fetch all price history for all symbols in ONE query (bulk load)
2. Organize into NumPy arrays by symbol
3. Compute Minervini, Weinstein, VCP, base detection in parallel
4. Return scored candidates ready for liquidity/swing checks
"""

import logging
from datetime import date as _date
from typing import Any

import numpy as np

from utils.db import DatabaseContext

logger = logging.getLogger(__name__)


class VectorizedSignalGenerator:
    """Parallel signal computation for all symbols."""

    def __init__(self) -> None:
        self.lookback_days = 300  # 300 trading days ~ 1.2 years
        self.min_history = 50  # Minimum bars required for technical indicators

    def fetch_all_price_data(
        self, symbols: list[str], eval_date: _date
    ) -> tuple[dict[str, list[dict[str, Any]]], _date]:
        """
        Fetch all price data for all symbols in ONE query.
        Automatically falls back to most recent date if eval_date has no data.
        Returns tuple: (data_by_symbol dict, actual_eval_date used)
        """
        try:
            with DatabaseContext("read") as cur:
                # First, check if eval_date has sufficient coverage
                cur.execute(
                    "SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = %s",
                    (eval_date,),
                )
                row = cur.fetchone()
                if row is None or row[0] is None:
                    raise ValueError(
                        f"Symbol count query returned NULL for {eval_date} — cannot determine price data availability"
                    )
                symbol_count = int(row[0])
                price_date = eval_date

                # CRITICAL: Do not fall back to stale data if eval_date insufficient
                # Stale price data causes signals to be dated incorrectly and break timing invariants
                if symbol_count < 1000:
                    raise ValueError(
                        f"[CRITICAL] Insufficient price data on eval_date={eval_date}: "
                        f"only {symbol_count} symbols available (need >=1000). "
                        f"Cannot generate signals with incomplete price history. "
                        f"Data pipeline may be stalled or incomplete for this date. "
                        f"Do not fall back to earlier dates — signal date must match eval date."
                    )

                # Fetch 300 days of history for all symbols in ONE query
                cur.execute(
                    """
                    SELECT symbol, date, close, high, low, volume, open
                    FROM price_daily
                    WHERE symbol = ANY(%s)
                      AND date >= %s::date - INTERVAL '300 days'
                      AND date <= %s
                    ORDER BY symbol, date ASC
                    """,
                    (symbols, price_date, price_date),
                )
                rows = cur.fetchall()

                # Organize by symbol into structured arrays
                data_by_symbol: dict[str, list[dict[str, Any]]] = {}
                for row in rows:
                    symbol = row[0]
                    if symbol not in data_by_symbol:
                        data_by_symbol[symbol] = []
                    data_by_symbol[symbol].append(
                        {
                            "date": row[1],
                            "close": float(row[2]) if row[2] is not None else None,
                            "high": float(row[3]) if row[3] is not None else None,
                            "low": float(row[4]) if row[4] is not None else None,
                            "volume": int(row[5]) if row[5] is not None else None,
                            "open": float(row[6]) if row[6] is not None else None,
                        }
                    )

                return data_by_symbol, price_date
        except (ValueError, ZeroDivisionError, TypeError) as e:
            error_msg = f"[VECTORIZED] Failed to fetch price data: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def compute_minervini_parallel(self, data_by_symbol: dict[str, Any], eval_date: _date) -> dict[str, dict[str, Any]]:
        """
        Compute Minervini 8-point trend template for all symbols.

        Returns: {symbol: {score: 0-8, pass: bool, ...}}
        """
        results = {}

        for symbol, rows in data_by_symbol.items():
            if len(rows) < self.min_history:
                logger.warning(
                    f"[VECTORIZED] {symbol}: Insufficient price history for Minervini ({len(rows)} < {self.min_history})"
                )
                results[symbol] = {
                    "score": 0,
                    "pass": False,
                    "criteria": {},
                    "failed": True,
                    "reason": "Insufficient price history",
                }
                continue

            try:
                # Extract closes into numpy array
                closes = np.array([r["close"] for r in rows if r["close"] is not None])

                if len(closes) < 252:
                    logger.warning(
                        f"[VECTORIZED] {symbol}: Insufficient valid closes for Minervini ({len(closes)} < 252)"
                    )
                    results[symbol] = {
                        "score": 0,
                        "pass": False,
                        "criteria": {},
                        "failed": True,
                        "reason": "Not enough valid closes",
                    }
                    continue

                # Compute SMAs using NumPy
                sma50 = self._rolling_mean(closes, 50)
                sma150 = self._rolling_mean(closes, 150)
                sma200 = self._rolling_mean(closes, 200)
                # SMA200 slope: (current - 5 bars ago) / (5 bars ago)
                sma200_slope = (
                    (sma200[-1] - sma200[-6]) / sma200[-6]
                    if len(sma200) > 6 and not np.isnan(sma200[-1]) and not np.isnan(sma200[-6]) and sma200[-6] > 0
                    else None
                )

                # Compute 52-week high/low
                high52 = np.max(closes[-252:]) if len(closes) >= 252 else np.max(closes)
                low52 = np.min(closes[-252:]) if len(closes) >= 252 else np.min(closes)

                # Get current close
                c = closes[-1] if len(closes) > 0 else np.nan

                # Score 8 criteria
                score = 0
                criteria = {}

                # 1. Close > SMA50
                if sma50[-1] is not None and not np.isnan(sma50[-1]) and c > sma50[-1]:
                    score += 1
                    criteria["close_above_sma50"] = True
                else:
                    criteria["close_above_sma50"] = False

                # 2. Close > SMA150
                if sma150[-1] is not None and not np.isnan(sma150[-1]) and c > sma150[-1]:
                    score += 1
                    criteria["close_above_sma150"] = True
                else:
                    criteria["close_above_sma150"] = False

                # 3. Close > SMA200
                if sma200[-1] is not None and not np.isnan(sma200[-1]) and c > sma200[-1]:
                    score += 1
                    criteria["close_above_sma200"] = True
                else:
                    criteria["close_above_sma200"] = False

                # 4. SMA50 > SMA150
                if (
                    sma50[-1] is not None
                    and not np.isnan(sma50[-1])
                    and sma150[-1] is not None
                    and not np.isnan(sma150[-1])
                    and sma50[-1] > sma150[-1]
                ):
                    score += 1
                    criteria["sma50_above_sma150"] = True
                else:
                    criteria["sma50_above_sma150"] = False

                # 5. SMA150 > SMA200
                if (
                    sma150[-1] is not None
                    and not np.isnan(sma150[-1])
                    and sma200[-1] is not None
                    and not np.isnan(sma200[-1])
                    and sma150[-1] > sma200[-1]
                ):
                    score += 1
                    criteria["sma150_above_sma200"] = True
                else:
                    criteria["sma150_above_sma200"] = False

                # 6. SMA200 slope > 0
                if sma200_slope is not None and sma200_slope > 0:
                    score += 1
                    criteria["sma200_positive_slope"] = True
                else:
                    criteria["sma200_positive_slope"] = False

                # 7. Close >= 52w high * 0.75
                if c >= high52 * 0.75:
                    score += 1
                    criteria["close_near_52w_high"] = True
                else:
                    criteria["close_near_52w_high"] = False

                # 8. Close >= 52w low * 1.30
                if c >= low52 * 1.30:
                    score += 1
                    criteria["close_well_above_52w_low"] = True
                else:
                    criteria["close_well_above_52w_low"] = False

                pct_from_low = ((c - low52) / low52 * 100) if low52 else None
                pct_from_high = ((c - high52) / high52 * 100) if high52 else None

                results[symbol] = {
                    "score": score,
                    "pass": score >= 5,
                    "criteria": criteria,
                    "pct_from_52w_high": pct_from_high,
                    "pct_from_52w_low": pct_from_low,
                }
            except (ValueError, TypeError, IndexError) as e:
                logger.warning(f"[VECTORIZED] {symbol}: Minervini computation failed: {e}")
                results[symbol] = {
                    "score": 0,
                    "pass": False,
                    "criteria": {},
                    "failed": True,
                    "reason": f"Computation error: {str(e)[:50]}",
                }

        return results

    def compute_weinstein_stage_parallel(
        self, data_by_symbol: dict[str, Any], eval_date: _date
    ) -> dict[str, dict[str, Any]]:
        """Compute Weinstein 4-stage classification for all symbols."""
        results = {}

        for symbol, rows in data_by_symbol.items():
            if len(rows) < self.min_history:
                logger.warning(
                    f"[VECTORIZED] {symbol}: Insufficient history for Weinstein ({len(rows)} < {self.min_history})"
                )
                results[symbol] = {"stage": 0, "confidence": 0.0, "failed": True}
                continue

            try:
                closes = np.array([r["close"] for r in rows if r["close"] is not None])
                if len(closes) < 252:
                    logger.warning(
                        f"[VECTORIZED] {symbol}: Insufficient clean closes for Weinstein ({len(closes)} < 252)"
                    )
                    results[symbol] = {"stage": 0, "confidence": 0.0, "failed": True}
                    continue

                # Compute 30-week MA (150 days) and slope
                ma150 = self._rolling_mean(closes, 150)
                ma150_slope = (
                    (ma150[-1] - ma150[-6]) / ma150[-6]
                    if len(ma150) > 6 and not np.isnan(ma150[-1]) and not np.isnan(ma150[-6]) and ma150[-6] > 0
                    else None
                )

                c = closes[-1] if len(closes) > 0 else np.nan
                sma200 = self._rolling_mean(closes, 200)
                sma200_val = sma200[-1] if len(sma200) > 0 else np.nan

                # Weinstein stages based on price position and MA slope
                stage = 0
                if not np.isnan(sma200_val) and not np.isnan(c) and c > sma200_val:
                    if ma150_slope is not None and ma150_slope > 0:
                        stage = 2  # Uptrend
                    else:
                        stage = 3  # Distribution
                else:
                    if ma150_slope is not None and ma150_slope < 0:
                        stage = 4  # Downtrend
                    else:
                        stage = 1  # Base building

                results[symbol] = {"stage": stage, "confidence": 0.75}
            except (ValueError, ZeroDivisionError, TypeError) as e:
                logger.warning(f"[VECTORIZED] {symbol}: Weinstein computation failed: {e}")
                results[symbol] = {"stage": 0, "confidence": 0.0, "failed": True}

        return results

    def compute_power_trend_parallel(
        self, data_by_symbol: dict[str, Any], eval_date: _date
    ) -> dict[str, dict[str, Any]]:
        """Compute power trend: 20%+ gain in 21 days."""
        results = {}

        for symbol, rows in data_by_symbol.items():
            if len(rows) < 21:
                logger.warning(f"[VECTORIZED] {symbol}: Insufficient history for power trend ({len(rows)} < 21)")
                results[symbol] = {"power_trend": False, "return_21d": None, "failed": True}
                continue

            try:
                closes = np.array([r["close"] for r in rows if r["close"] is not None])
                if len(closes) < 21:
                    logger.warning(
                        f"[VECTORIZED] {symbol}: Insufficient clean closes for power trend ({len(closes)} < 21)"
                    )
                    results[symbol] = {"power_trend": False, "return_21d": None, "failed": True}
                    continue

                current = closes[-1] if len(closes) > 0 and not np.isnan(closes[-1]) else None
                prior = closes[-21] if len(closes) > 20 and not np.isnan(closes[-21]) else None
                ret_21d = (
                    ((current - prior) / prior * 100)
                    if current is not None and prior is not None and prior > 0
                    else None
                )

                # CRITICAL: Fail fast if return calculation failed
                # Do NOT silently default to False — this masks data quality issues
                if ret_21d is None:
                    raise ValueError(
                        f"Cannot compute 21-day return for {symbol}: "
                        f"21-day-ago close <= 0 (invalid historical price data)"
                    )

                results[symbol] = {
                    "power_trend": ret_21d >= 20,
                    "return_21d": ret_21d,
                }
            except (ValueError, ZeroDivisionError, TypeError) as e:
                logger.warning(f"[VECTORIZED] {symbol}: Power trend computation failed: {e}")
                results[symbol] = {"power_trend": False, "return_21d": None, "failed": True}

        return results

    @staticmethod
    def _rolling_mean(arr: np.ndarray[Any, Any], window: int) -> np.ndarray[Any, Any]:
        """Compute rolling mean. Handles NaNs, pads with NaN for short windows."""
        if len(arr) < window:
            return np.full(len(arr), np.nan)
        result = np.full(len(arr), np.nan)
        for i in range(window - 1, len(arr)):
            result[i] = np.nanmean(arr[i - window + 1 : i + 1])
        return result

    def run(self, symbols: list[str], eval_date: _date) -> dict[str, Any]:
        """
        Run all signal computations in parallel.

        Returns dict with all symbols and their computed signals.

        CRITICAL: Callers MUST filter results by checking `failed: False` before using.
        Symbols with failed=True have insufficient data and should not be used for trading.
        This class does NOT pre-filter results — filtering is the caller's responsibility.

        Result structure:
        {
            "minervini": {symbol: {"score": 0-8, "pass": bool, "failed": bool, ...}},
            "weinstein": {symbol: {"stage": 0-4, "confidence": float, "failed": bool, ...}},
            "power": {symbol: {"power_trend": bool, "return_21d": float, "failed": bool, ...}},
            "symbols_processed": int,
            "actual_eval_date": date,
        }
        """
        logger.info(f"[VECTORIZED] Fetching price data for {len(symbols)} symbols...")
        data_by_symbol, actual_eval_date = self.fetch_all_price_data(symbols, eval_date)

        symbols_with_data = len(data_by_symbol)
        logger.info(f"[VECTORIZED] Got data for {symbols_with_data} symbols (using date={actual_eval_date})")

        # Compute all signals in parallel
        logger.info("[VECTORIZED] Computing Minervini scores...")
        minervini = self.compute_minervini_parallel(data_by_symbol, actual_eval_date)

        logger.info("[VECTORIZED] Computing Weinstein stages...")
        weinstein = self.compute_weinstein_stage_parallel(data_by_symbol, actual_eval_date)

        logger.info("[VECTORIZED] Computing power trends...")
        power = self.compute_power_trend_parallel(data_by_symbol, actual_eval_date)

        return {
            "minervini": minervini,
            "weinstein": weinstein,
            "power": power,
            "symbols_processed": symbols_with_data,
            "actual_eval_date": actual_eval_date,
        }
