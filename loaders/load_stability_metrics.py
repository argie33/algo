#!/usr/bin/env python3
"""Stability Metrics Loader - Volatility and Beta (both from price_daily).

Computes:
- 30-day volatility: rolling std dev of daily returns
- 60-day volatility: rolling std dev of daily returns
- 252-day volatility: rolling std dev of daily returns (1 year)
- Beta: relative to S&P 500 computed from price_daily (SPY correlation, no yfinance)

Requires: price_daily table populated with at least 30 days of data (252 for full year vol).
Beta is computed as Cov(stock_returns, spy_returns) / Var(spy_returns) from price_daily.
"""

import sys

import psycopg2

from loaders.loader_helper import setup_imports

setup_imports()

import logging  # noqa: E402
import math  # noqa: E402
from datetime import date, datetime, timezone  # noqa: E402
from typing import Any, cast  # noqa: E402

from loaders.runner import run_loader  # noqa: E402
from utils.db.context import DatabaseContext  # noqa: E402
from utils.optimal_loader import OptimalLoader  # noqa: E402

logger = logging.getLogger(__name__)


class StabilityMetricsLoader(OptimalLoader):
    """Compute volatility and beta metrics."""

    table_name = "stability_metrics"
    primary_key = ("symbol",)
    watermark_field = "created_at"
    exclude_etfs_from_symbols = True  # ETFs excluded: most lack sufficient price history for beta

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Compute stability metrics for this symbol.

        For OPTIONAL enrichment (beta/volatility): Returns explicit data_unavailable marker
        instead of raising errors, enabling graceful degradation when metrics unavailable.

        Returns list containing:
        - Valid metrics dict if successful (data_unavailable=False)
        - data_unavailable marker dict if unable to compute (e.g., <30 days price history)
        """
        try:
            metrics = self._compute_stability_metrics(symbol)
            return [metrics]
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(
                f"[STABILITY_METRICS] Database error for {symbol}: {e}. "
                f"Stability metrics (beta/volatility) are optional enrichment - marking unavailable."
            )
            return [
                {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": f"database_error: {str(e)[:100]}",
                    "volatility_30d": None,
                    "volatility_60d": None,
                    "volatility_252d": None,
                    "beta": None,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            ]
        except RuntimeError as e:
            # Insufficient data (< 30 days) or validation error
            logger.debug(f"[STABILITY_METRICS] {symbol}: {e}. Stability metrics unavailable (optional enrichment).")
            return [
                {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": str(e)[:150],
                    "volatility_30d": None,
                    "volatility_60d": None,
                    "volatility_252d": None,
                    "beta": None,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            ]
        except Exception as e:
            logger.warning(
                f"[STABILITY_METRICS] Unexpected error computing metrics for {symbol}: {type(e).__name__}: {e}. "
                f"Marking stability metrics as unavailable (optional enrichment)."
            )
            return [
                {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": f"unexpected_error: {type(e).__name__}",
                    "volatility_30d": None,
                    "volatility_60d": None,
                    "volatility_252d": None,
                    "beta": None,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            ]

    def _compute_stability_metrics(self, symbol: str) -> dict[str, Any]:
        """Compute volatility from price_daily and beta from price_daily (SPY correlation).

        Beta is computed by regressing stock daily returns against SPY daily returns from
        price_daily — no yfinance calls. This eliminates yfinance rate-limiting timeouts
        that caused 95%+ symbol failures when fetching beta via external API.

        For OPTIONAL enrichment: Returns explicit data_unavailable marker instead of raising
        when data cannot be computed (e.g., insufficient price history).

        Minimum requirement: 30 days of price history for meaningful volatility calculation.
        """
        try:
            with DatabaseContext("read") as cur:
                # Fetch last 252 trading days of price data
                cur.execute(
                    """
                    SELECT date, close FROM price_daily
                    WHERE symbol = %s
                    ORDER BY date DESC
                    LIMIT 252
                """,
                    (symbol,),
                )
                rows = cur.fetchall()

                # Fetch SPY prices for the same date range to compute beta from DB.
                # This replaces the yfinance beta call which caused 95%+ symbol timeouts
                # due to rate limiting (each yfinance call hung for 60-120s per symbol).
                spy_rows: list[Any] = []
                if rows:
                    stock_dates = [row[0] for row in rows]
                    min_date = min(stock_dates)
                    max_date = max(stock_dates)
                    cur.execute(
                        """
                        SELECT date, close FROM price_daily
                        WHERE symbol = 'SPY'
                          AND date >= %s AND date <= %s
                        ORDER BY date ASC
                        """,
                        (min_date, max_date),
                    )
                    spy_rows = cur.fetchall()

            # Require minimum 5 days of data for volatility calculation
            # Rationale: New IPOs with only 1 week of data still need stability scores
            # 5 days is the minimum for computing a meaningful daily return-based volatility
            # Most volatility will be calculated from whatever data is available (even <30 days)
            # For new listings with <30 days, 30d volatility will be unavailable (optional metric)
            if not rows or len(rows) < 5:
                actual_rows = len(rows) if rows else 0
                raise RuntimeError(f"insufficient_price_history: {actual_rows}/5 days available")

            # Sort chronologically (oldest to newest)
            prices = sorted(
                [
                    (
                        (date(row[0].year, row[0].month, row[0].day) if hasattr(row[0], "year") else row[0]),
                        float(row[1]),
                    )
                    for row in rows
                ]
            )

            # Calculate returns
            returns = []
            for i in range(1, len(prices)):
                if prices[i - 1][1] > 0:
                    ret = math.log(prices[i][1] / prices[i - 1][1])
                    returns.append(ret)

            if not returns:
                raise RuntimeError("invalid_price_data: no valid price transitions")

            # Calculate volatilities (annualized: sqrt(252) * daily_std)
            # For new listings: use whatever data is available (minimum 2 returns for volatility)
            # Helper methods now return float or explicit marker dict for data_unavailable
            volatility_30d_result: float | dict[str, Any]
            if len(returns) < 30:
                volatility_30d_result = {
                    "data_unavailable": True,
                    "reason": f"insufficient_returns ({len(returns)}/30 required)",
                }
            else:
                volatility_30d_result = self._calculate_volatility(returns[-30:], symbol=symbol)

            volatility_60d_result: float | dict[str, Any]
            if len(returns) < 60:
                volatility_60d_result = {
                    "data_unavailable": True,
                    "reason": f"insufficient_returns ({len(returns)}/60 required)",
                }
            else:
                volatility_60d_result = self._calculate_volatility(returns[-60:], symbol=symbol)
            # For 252d (full year) volatility: use all available data if present (minimum 2 returns)
            # Even new listings with 3+ days (2 returns) can compute a volatility estimate
            volatility_252d_result = self._calculate_volatility(returns, symbol=symbol) if len(returns) >= 2 else None
            beta_result = self._get_beta_from_db(symbol, prices, spy_rows)

            # Unpack results: distinguish between numeric values and marker dicts
            volatility_30d: float | None = None if isinstance(volatility_30d_result, dict) else volatility_30d_result
            volatility_60d: float | None = None if isinstance(volatility_60d_result, dict) else volatility_60d_result

            # For 252d and beta, check if they're marker dicts indicating unavailability
            volatility_252d_unavailable = isinstance(volatility_252d_result, dict) and volatility_252d_result.get(
                "data_unavailable"
            )
            beta_unavailable = isinstance(beta_result, dict) and beta_result.get("data_unavailable")

            # Type narrow: if not dict, must be float (or None for 252d)
            volatility_252d: float | None = (
                None
                if volatility_252d_unavailable
                else (volatility_252d_result if isinstance(volatility_252d_result, float) else None)
            )
            beta: float | None = None if beta_unavailable else (beta_result if isinstance(beta_result, float) else None)

            # STRICT: Stability metrics require COMPLETE data (all three volatilities + beta)
            # Partial metrics lead to inaccurate risk calculations. No fallback to degraded data.
            unavailability_reasons = []

            # Check 30d volatility availability
            volatility_30d_unavailable = isinstance(volatility_30d_result, dict) and volatility_30d_result.get(
                "data_unavailable"
            )
            if volatility_30d_unavailable:
                if not isinstance(volatility_30d_result, dict) or "reason" not in volatility_30d_result:
                    reason_30d = "missing_reason_field"
                else:
                    reason_30d = volatility_30d_result["reason"]
                unavailability_reasons.append(f"vol_30d: {reason_30d}")

            # Check 60d volatility availability
            volatility_60d_unavailable = isinstance(volatility_60d_result, dict) and volatility_60d_result.get(
                "data_unavailable"
            )
            if volatility_60d_unavailable:
                if not isinstance(volatility_60d_result, dict) or "reason" not in volatility_60d_result:
                    reason_60d = "missing_reason_field"
                else:
                    reason_60d = volatility_60d_result["reason"]
                unavailability_reasons.append(f"vol_60d: {reason_60d}")

            if volatility_252d_unavailable:
                if not isinstance(volatility_252d_result, dict) or "reason" not in volatility_252d_result:
                    reason_252d = "missing_reason_field"
                else:
                    reason_252d = volatility_252d_result["reason"]
                unavailability_reasons.append(f"vol_252d: {reason_252d}")

            if beta_unavailable:
                if not isinstance(beta_result, dict) or "reason" not in beta_result:
                    reason_beta = "missing_reason_field"
                else:
                    reason_beta = beta_result["reason"]
                unavailability_reasons.append(f"beta: {reason_beta}")

            # FAIL-FAST: Missing ANY component makes all stability metrics unavailable
            # Partial metrics compromise risk accuracy
            has_complete_metrics = (
                volatility_30d is not None and
                volatility_60d is not None and
                volatility_252d is not None and
                beta is not None
            )
            data_unavailable = not has_complete_metrics
            reason = "; ".join(unavailability_reasons) if unavailability_reasons else None

            if data_unavailable:
                logger.debug(
                    f"[STABILITY_METRICS] {symbol}: incomplete metrics "
                    f"(vol_252d={not volatility_252d_unavailable}, beta={not beta_unavailable}). "
                    f"Reasons: {reason}"
                )

            return {
                "symbol": symbol,
                "volatility_30d": round(volatility_30d, 4) if volatility_30d else None,
                "volatility_60d": round(volatility_60d, 4) if volatility_60d else None,
                "volatility_252d": (round(volatility_252d, 4) if volatility_252d else None),
                "beta": round(beta, 4) if beta else None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "data_unavailable": data_unavailable,
                "reason": reason,
            }

        except RuntimeError as e:
            # Data unavailability (insufficient history, invalid data)
            raise RuntimeError(str(e)) from e
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(f"calculation_error: {type(e).__name__}") from e

    @staticmethod
    def _calculate_volatility(returns: list[float], symbol: str = "") -> float | dict[str, Any]:
        """Calculate annualized volatility from returns.

        For optional periods (30d, 60d): Returns explicit marker dict if insufficient data
        For full year (252d): Raises ValueError if insufficient data (required field)

        Args:
            returns: List of daily returns (log returns)
            symbol: Symbol name for marker dict (required for unavailability tracking)

        Returns:
            Annualized volatility (float) or explicit marker dict if data unavailable

        Raises:
            ValueError: If full year (252d) volatility cannot be calculated
        """
        if not returns or len(returns) < 2:
            # Return explicit unavailability marker when insufficient data
            actual_returns = len(returns) if returns else 0
            logger.debug(
                f"[STABILITY_METRICS] {symbol or 'unknown'}: insufficient returns ({actual_returns}) "
                f"for volatility calculation (minimum 2 required)"
            )
            return {
                "symbol": symbol or "unknown",
                "data_unavailable": True,
                "reason": f"insufficient_returns: {actual_returns}/2 minimum required",
            }

        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        daily_std = math.sqrt(variance)

        # Annualize: multiply by sqrt(252)
        return daily_std * math.sqrt(252)

    @staticmethod
    def _get_beta_from_db(
        symbol: str,
        stock_prices: list[tuple[Any, float]],
        spy_rows: list[Any],
    ) -> float | dict[str, Any]:
        """Compute beta from price_daily by regressing stock returns against SPY returns.

        Replaces yfinance beta fetch to eliminate external API rate-limiting timeouts.
        Beta = Cov(stock_returns, spy_returns) / Var(spy_returns) over shared trading days.

        Args:
            symbol: Ticker symbol (for logging/markers).
            stock_prices: List of (date, close) tuples sorted chronologically from price_daily.
            spy_rows: SPY price rows from price_daily for the same date range.
        """
        import numpy as np

        # For new listings: allow beta calculation with as few as 5 overlapping days with SPY
        # Full beta calculation (30+ days) is more accurate, but partial data is better than nothing
        min_spy_days = 5
        if not spy_rows or len(spy_rows) < min_spy_days:
            actual = len(spy_rows) if spy_rows else 0
            logger.debug(
                f"[STABILITY_METRICS] {symbol}: SPY price data insufficient ({actual} rows). "
                f"Beta unavailable (requires {min_spy_days}+ overlapping days)."
            )
            return {
                "symbol": symbol,
                "data_unavailable": True,
                "reason": f"spy_price_data_insufficient: {actual}/{min_spy_days} days",
            }

        try:
            stock_by_date = {p[0]: p[1] for p in stock_prices}
            spy_by_date: dict[Any, float] = {}
            for row in spy_rows:
                d = row[0].date() if hasattr(row[0], "date") else row[0]
                spy_by_date[d] = float(row[1])

            common_dates = sorted(set(stock_by_date.keys()) & set(spy_by_date.keys()))
            # For new listings: allow beta calculation with as few as 5 common trading dates
            min_common_dates = 5
            if len(common_dates) < min_common_dates:
                return {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": f"insufficient_common_dates: {len(common_dates)}/{min_common_dates}",
                }

            stock_aligned = [stock_by_date[d] for d in common_dates]
            spy_aligned = [spy_by_date[d] for d in common_dates]

            stock_returns = np.diff(np.log(np.array(stock_aligned, dtype=float)))
            spy_returns = np.diff(np.log(np.array(spy_aligned, dtype=float)))

            # For new listings: allow beta calculation with as few as 4 returns (5 common dates)
            min_returns = 4
            if len(stock_returns) < min_returns:
                return {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": f"insufficient_returns: {len(stock_returns)}/{min_returns}",
                }

            spy_var = float(np.var(spy_returns, ddof=1))
            if spy_var == 0:
                return {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": "spy_variance_zero",
                }

            cov_matrix = np.cov(stock_returns, spy_returns)
            beta = float(cov_matrix[0, 1]) / spy_var

            if abs(beta) > 10:
                logger.debug(f"[STABILITY_METRICS] {symbol}: extreme DB beta {beta:.2f} — marking unavailable.")
                return {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": f"extreme_beta: {beta:.2f}",
                }

            return round(beta, 4)

        except Exception as e:
            logger.warning(f"[STABILITY_METRICS] {symbol}: DB beta computation failed: {type(e).__name__}: {e}")
            return {
                "symbol": symbol,
                "data_unavailable": True,
                "reason": f"db_beta_error: {type(e).__name__}",
            }

    def transform(self, rows: Any) -> list[dict[str, Any]]:
        """Rows are clean."""
        return cast(list[dict[str, Any]], rows)

    def _validate_row(self, row: dict[str, Any]) -> bool:
        """Validate stability metrics row.

        Ensures symbol field exists (required). Validates that data_unavailable marker
        is explicitly set (never silent/implicit availability).
        """
        if not super()._validate_row(row):
            return False

        # Validate symbol exists (required field, not optional)
        symbol = row.get("symbol")
        if symbol is None:
            logger.error("[STABILITY_METRICS] Invalid row: symbol field missing or None")
            return False

        # Validate data_unavailable marker is explicit
        if "data_unavailable" not in row:
            logger.error(
                f"[STABILITY_METRICS] Invalid row for {symbol}: "
                f"data_unavailable marker missing (must be explicit: True or False)"
            )
            return False

        return True


if __name__ == "__main__":
    sys.exit(run_loader(StabilityMetricsLoader))
