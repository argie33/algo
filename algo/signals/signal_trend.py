#!/usr/bin/env python3

"""
Trend signal methods — Minervini trend template, Weinstein stage, Mansfield RS.

These methods read from pre-computed trend_template_data (populated by loaders)
and compute Mansfield RS on-demand using price returns. Falls back to on-the-fly
computation if trend_template_data is stale.
"""

import logging
from typing import Any, cast

import psycopg2

from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)


class SignalTrendMixin:
    """Trend signal methods reading from pre-computed data and real-time calculations."""

    def _with_cursor(self, operation: Any) -> Any:
        """Execute an operation with a cursor via DatabaseContext."""
        try:
            with DatabaseContext("read") as cur:
                return operation(cur)
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    @staticmethod
    def _is_valid_float(v: Any) -> bool:
        """Check if a value can be safely converted to float."""
        try:
            float(v)
            return True
        except (TypeError, ValueError):
            return False

    def _compute_minervini_from_prices(self, cur: Any, symbol: str, eval_date: Any) -> dict[str, Any]:
        """Compute Minervini 8-point trend score on-the-fly from price_daily."""
        cur.execute(
            """SELECT date, close, volume FROM price_daily
               WHERE symbol = %s AND date >= %s::date - INTERVAL '300 days'
               AND date <= %s
               ORDER BY date ASC""",
            (symbol, eval_date, eval_date),
        )
        rows = cur.fetchall()
        if not rows or len(rows) < 200:
            raise ValueError(
                f"Minervini trend calculation failed for {symbol}: "
                f"insufficient price history ({len(rows) if rows else 0} days, need 200+ for SMA200)"
            )

        import numpy as np

        closes_raw = [row[1] for row in rows]
        try:
            close = np.array([float(v) for v in closes_raw], dtype=np.float64)
        except (TypeError, ValueError) as e:
            invalid_indices = [i for i, v in enumerate(closes_raw) if not self._is_valid_float(v)]
            raise ValueError(
                f"Invalid price data for {symbol}: {len(invalid_indices)} "
                f"non-numeric values at indices {invalid_indices[:5]}{'...' if len(invalid_indices) > 5 else ''}. "
                f"Cannot silently drop data points (breaks date alignment). "
                f"Original error: {e}"
            ) from e

        close = close[np.isfinite(close)]
        if len(close) < 200:
            raise ValueError(
                f"Minervini trend calculation failed for {symbol}: "
                f"insufficient non-NaN price data ({len(close)} valid points after filtering, need 200+ for SMA200)"
            )

        def _sma(arr: Any, n: int) -> float | None:
            if len(arr) < n:
                return None
            return float(np.mean(arr[-n:]))

        c = float(close[-1])
        sma50 = _sma(close, 50)
        sma150 = _sma(close, 150)
        sma200 = _sma(close, 200)
        high52 = float(np.max(close[-252:])) if len(close) >= 252 else None
        low52 = float(np.min(close[-252:])) if len(close) >= 252 else None

        sma200_slope = None
        if sma200 is not None and len(close) >= 205:
            sma200_5ago = float(np.mean(close[-205:-5]))
            if sma200_5ago > 0:
                sma200_slope = (sma200 - sma200_5ago) / sma200_5ago

        score = 0
        if sma50 and c > sma50:
            score += 1
        if sma150 and c > sma150:
            score += 1
        if sma200 and c > sma200:
            score += 1
        if sma50 and sma150 and sma50 > sma150:
            score += 1
        if sma150 and sma200 and sma150 > sma200:
            score += 1
        if sma200_slope is not None and sma200_slope > 0:
            score += 1
        if high52 and c >= high52 * 0.75:
            score += 1
        if low52 and c >= low52 * 1.30:
            score += 1

        pct_from_low = ((c - low52) / low52 * 100) if low52 else None
        pct_from_high = ((c - high52) / high52 * 100) if high52 else None

        if sma200 and c > sma200:
            if sma200_slope is not None and sma200_slope > 0:
                weinstein_stage = 2
            else:
                weinstein_stage = 3
        else:
            if sma200_slope is not None and sma200_slope < 0:
                weinstein_stage = 4
            else:
                weinstein_stage = 1

        return {
            "score": score,
            "pass": score >= 5,
            "criteria": {
                "percent_from_52w_high": (float(pct_from_high) if pct_from_high is not None else None),
                "percent_from_52w_low": (float(pct_from_low) if pct_from_low is not None else None),
                "weinstein_stage": weinstein_stage,
                "trend_direction": ("uptrend" if score >= 6 else ("downtrend" if score <= 2 else "sideways")),
            },
        }

    def minervini_trend_template(self, symbol: str, eval_date: Any) -> dict[str, Any]:
        def _fetch_trend(cur: Any) -> dict[str, Any]:
            cur.execute(
                """SELECT minervini_trend_score, percent_from_52w_high, percent_from_52w_low,
                          weinstein_stage, trend_direction, date
                   FROM trend_template_data
                   WHERE symbol = %s AND date <= %s
                   ORDER BY date DESC LIMIT 1""",
                (symbol, eval_date),
            )
            row = cur.fetchone()
            if row and row[5] and (eval_date - row[5]).days <= 1:
                if row[0] is None:
                    raise ValueError(
                        f"CRITICAL: Minervini trend score is NULL for {symbol} on cached data. "
                        f"Trend template data is corrupt or incomplete."
                    )
                score = int(row[0])
                return {
                    "score": score,
                    "pass": score >= 5,
                    "criteria": {
                        "percent_from_52w_high": float(row[1]) if row[1] else None,
                        "percent_from_52w_low": float(row[2]) if row[2] else None,
                        "weinstein_stage": int(row[3]) if row[3] else None,
                        "trend_direction": str(row[4]) if row[4] else None,
                    },
                }

            logger.debug(f"[MINERVINI] trend_template_data stale for {symbol}; computing on-the-fly")
            return self._compute_minervini_from_prices(cur, symbol, eval_date)

        return cast(dict[str, Any], self._with_cursor(_fetch_trend))

    def weinstein_stage(self, symbol: str, eval_date: Any) -> dict[str, Any]:
        """
        Read pre-computed Weinstein 4-stage classification from trend_template_data.

        Stages: 1 (downtrend), 2 (uptrend), 3 (peak/top), 4 (recovery)

        Returns: {
            'stage': int (1-4),
            'confidence': float,
            'price_vs_ma_pct': float,
            'slope_pct': float,
        }
        """

        def _fetch_stage(cur: Any) -> dict[str, Any]:
            cur.execute(
                """SELECT weinstein_stage, consolidation_flag
                   FROM trend_template_data
                   WHERE symbol = %s AND date <= %s
                   ORDER BY date DESC LIMIT 1""",
                (symbol, eval_date),
            )
            row = cur.fetchone()
            if not row or not row[0]:
                raise ValueError(
                    f"Weinstein stage classification unavailable for {symbol} on {eval_date} — "
                    f"technical analysis required to determine market stage"
                )

            stage = int(row[0])
            # consolidation_flag=True means stock is building a base (early phase, higher confidence)
            confidence = 1.0 if row[1] else 0.5

            return {
                "stage": stage,
                "confidence": confidence,
                "price_vs_ma_pct": None,
                "slope_pct": None,
            }

        return cast(dict[str, Any], self._with_cursor(_fetch_stage))

    def mansfield_rs(self, symbol: str, eval_date: Any, lookback: int = 252) -> dict[str, Any]:
        """
        Compute Mansfield Relative Strength: (stock_return / spy_return) - 1.

        Measures how much better/worse the stock performed vs SPY over lookback period.
        Positive RS = outperforming market
        Negative RS = underperforming market

        Returns: {
            'mansfield_rs': float,
            'positive': bool,
            'stock_return_pct': float,
            'spy_return_pct': float,
        }
        """

        def _compute_rs(cur: Any) -> dict[str, Any]:
            try:
                stock_ret = self._period_return(cur, symbol, eval_date, lookback)  # type: ignore[attr-defined]
            except (ValueError, RuntimeError) as e:
                raise ValueError(
                    f"Mansfield RS calculation failed for {symbol}: could not compute stock return: {e}"
                ) from e

            try:
                spy_ret = self._period_return(cur, "SPY", eval_date, lookback)  # type: ignore[attr-defined]
            except (ValueError, RuntimeError) as e:
                raise ValueError(f"Mansfield RS calculation failed: could not compute SPY return: {e}") from e

            if spy_ret == 0:
                raise ValueError(
                    "Mansfield RS calculation failed: SPY return is zero (no price data for lookback period)"
                )

            mrs = (stock_ret / spy_ret) - 1
            return {
                "mansfield_rs": round(mrs, 4),
                "positive": mrs > 0,
                "stock_return_pct": round(stock_ret * 100, 2),
                "spy_return_pct": round(spy_ret * 100, 2),
            }

        return cast(dict[str, Any], self._with_cursor(_compute_rs))

    def stage2_phase(self, symbol: str, eval_date: Any) -> dict[str, Any]:
        """Alias for weinstein_stage() for backwards compatibility."""
        return self.weinstein_stage(symbol, eval_date)
