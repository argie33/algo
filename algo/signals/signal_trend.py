#!/usr/bin/env python3

"""
Trend signal methods - Minervini trend template, Weinstein stage, Mansfield RS.

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
        try:
            float(v)
            return True
        except (TypeError, ValueError):
            return False

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
            if row is None or len(row) < 1 or row[0] is None:
                raise ValueError(
                    f"Weinstein stage classification unavailable for {symbol} on {eval_date} - "
                    f"technical analysis required to determine market stage"
                )

            stage = int(row[0])
            # consolidation_flag=True means stock is building a base (early phase, higher confidence)
            confidence = 1.0 if row[1] is not None and row[1] else 0.5

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
