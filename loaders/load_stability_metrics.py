#!/usr/bin/env python3
"""Stability Metrics Loader - Volatility (from price_daily) and Beta (from yfinance).

Computes:
- 30-day volatility: rolling std dev of daily returns
- 60-day volatility: rolling std dev of daily returns
- 252-day volatility: rolling std dev of daily returns (1 year)
- Beta: relative to S&P 500 (from yfinance)

Requires: price_daily table populated with at least 252 days of data.
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
            logger.debug(
                f"[STABILITY_METRICS] {symbol}: {e}. "
                f"Stability metrics unavailable (optional enrichment)."
            )
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
        """Compute volatility from price_daily and beta from yfinance.

        For OPTIONAL enrichment: Returns explicit data_unavailable marker instead of raising
        when data cannot be computed (e.g., insufficient price history, yfinance unavailable).

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

            # Require minimum 30 days of data for meaningful volatility calculation
            if not rows or len(rows) < 30:
                actual_rows = len(rows) if rows else 0
                raise RuntimeError(
                    f"insufficient_price_history: {actual_rows}/30 days available"
                )

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
                raise RuntimeError(
                    "invalid_price_data: no valid price transitions"
                )

            # Calculate volatilities (annualized: sqrt(252) * daily_std)
            volatility_30d = self._calculate_volatility(returns[-30:]) if len(returns) >= 30 else None
            volatility_60d = self._calculate_volatility(returns[-60:]) if len(returns) >= 60 else None
            volatility_252d = self._calculate_volatility(returns, symbol=symbol)

            # Get beta from yfinance
            beta = self._get_beta_yfinance(symbol)

            return {
                "symbol": symbol,
                "volatility_30d": round(volatility_30d, 4) if volatility_30d else None,
                "volatility_60d": round(volatility_60d, 4) if volatility_60d else None,
                "volatility_252d": (round(volatility_252d, 4) if volatility_252d else None),
                "beta": round(beta, 4) if beta else None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "data_unavailable": False,
            }

        except RuntimeError as e:
            # Data unavailability (insufficient history, invalid data)
            raise RuntimeError(str(e)) from e
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(
                f"calculation_error: {type(e).__name__}"
            ) from e

    @staticmethod
    def _calculate_volatility(returns: list[float], symbol: str = "") -> float | None:
        """Calculate annualized volatility from returns.

        For optional periods (30d, 60d): Returns None if insufficient data
        For full year (252d): Raises ValueError if insufficient data (required field)

        Args:
            returns: List of daily returns (log returns)
            symbol: Optional symbol name for error messages (for 252d volatility failures)

        Returns:
            Annualized volatility (float) or None if optional period lacks data

        Raises:
            ValueError: If full year (252d) volatility cannot be calculated
        """
        if not returns or len(returns) < 2:
            # For optional periods (30d, 60d), returning None is acceptable
            # For full year (252d) used in scoring, this shouldn't happen
            if symbol:
                raise ValueError(
                    f"insufficient_returns: {len(returns) if returns else 0} returns (minimum 2 required)"
                )
            return None

        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        daily_std = math.sqrt(variance)

        # Annualize: multiply by sqrt(252)
        return daily_std * math.sqrt(252)

    @staticmethod
    def _get_beta_yfinance(symbol: str) -> float | None:
        """Fetch beta from yfinance via the rate-limiting wrapper.

        For OPTIONAL enrichment: Returns None if beta unavailable (instead of raising).
        This allows volatility metrics to be returned even if beta fetch fails.

        Uses ONLY primary 'beta' field (no fallback to beta3Year).
        Validates:
        - beta field exists (not fetched with .get() default)
        - beta value is not None
        - beta is not extreme (>200 indicates corruption)

        Raises RuntimeError if yfinance ticker cannot be fetched (permanent error).
        Returns None if beta data unavailable but ticker OK (transient/data error).
        """
        from utils.external.yfinance import get_ticker

        ticker = get_ticker(symbol)
        if not ticker:
            logger.warning(f"[STABILITY_METRICS] {symbol}: cannot fetch yfinance ticker data")
            return None

        try:
            info = ticker.info

            # Validate 'beta' field exists explicitly (not using .get() default)
            if "beta" not in info:
                logger.debug(f"[STABILITY_METRICS] {symbol}: beta field missing from yfinance data")
                return None

            beta_raw = info["beta"]

            # Validate value is not None
            if beta_raw is None:
                logger.debug(f"[STABILITY_METRICS] {symbol}: beta field is None (unavailable from yfinance)")
                return None

            # Convert to float and validate
            beta = float(beta_raw)

            # Reject extreme values that indicate data corruption
            if abs(beta) > 200:
                logger.warning(
                    f"[STABILITY_METRICS] {symbol}: extreme beta value {beta} (out of range [-200, 200]). "
                    f"Data appears corrupted - marking beta unavailable."
                )
                return None

            return beta
        except (ValueError, TypeError) as e:
            logger.debug(f"[STABILITY_METRICS] {symbol}: failed to parse beta ({type(e).__name__}: {e})")
            return None
        except ZeroDivisionError as e:
            logger.debug(f"[STABILITY_METRICS] {symbol}: division error parsing beta: {e}")
            return None
        except Exception as e:
            logger.warning(
                f"[STABILITY_METRICS] {symbol}: unexpected error fetching beta: {type(e).__name__}: {e}. "
                f"Beta calculation failed - stability metrics may be incomplete for this symbol."
            )
            return None

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
