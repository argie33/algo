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

        Raises RuntimeError if unable to compute (e.g., new symbol with <30 days price history).
        Caller must handle unavailable metrics explicitly.
        """
        try:
            metrics = self._compute_stability_metrics(symbol)
            return [metrics]
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"[STABILITY_METRICS] Database error for {symbol}: {e}")
            raise RuntimeError(
                f"[STABILITY_METRICS] Database error computing metrics for {symbol}: {e}. "
                f"Cannot compute stability metrics without price history access."
            ) from e
        except Exception as e:
            logger.error(
                f"[STABILITY_METRICS] Unexpected error computing metrics for {symbol}: {type(e).__name__}: {e}"
            )
            raise

    def _compute_stability_metrics(self, symbol: str) -> dict[str, Any]:
        """Compute volatility from price_daily and beta from yfinance.

        Requires minimum 30 days of price history. Raises if data insufficient.
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
                    f"[STABILITY_METRICS] {symbol}: insufficient price history ({actual_rows}/30 days required). "
                    f"Cannot compute stability metrics without adequate historical data."
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
                    f"[STABILITY_METRICS] {symbol}: cannot calculate returns (no valid price transitions). "
                    f"Price history contains invalid data."
                )

            # Calculate volatilities (annualized: sqrt(252) * daily_std)
            volatility_30d = self._calculate_volatility(returns[-30:]) if len(returns) >= 30 else None
            volatility_60d = self._calculate_volatility(returns[-60:]) if len(returns) >= 60 else None
            volatility_252d = self._calculate_volatility(returns)

            # Get beta from yfinance
            beta = self._get_beta_yfinance(symbol)

            return {
                "symbol": symbol,
                "volatility_30d": round(volatility_30d, 4) if volatility_30d else None,
                "volatility_60d": round(volatility_60d, 4) if volatility_60d else None,
                "volatility_252d": (round(volatility_252d, 4) if volatility_252d else None),
                "beta": round(beta, 4) if beta else None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

        except RuntimeError:
            raise
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(
                f"[STABILITY_METRICS] {symbol}: calculation error ({type(e).__name__}: {e}). "
                f"Cannot compute stability metrics with invalid data."
            ) from e

    @staticmethod
    def _calculate_volatility(returns: list[float]) -> float | None:
        """Calculate annualized volatility from returns."""
        if not returns or len(returns) < 2:
            return None

        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        daily_std = math.sqrt(variance)

        # Annualize: multiply by sqrt(252)
        return daily_std * math.sqrt(252)

    @staticmethod
    def _get_beta_yfinance(symbol: str) -> float:
        """Fetch beta from yfinance via the rate-limiting wrapper.

        Uses ONLY primary 'beta' field (no fallback to beta3Year).
        Validates:
        - beta field exists (not fetched with .get() default)
        - beta value is not None
        - beta is not extreme (>200 indicates corruption)

        Raises RuntimeError if beta unavailable or invalid.
        """
        from utils.external.yfinance import get_ticker

        ticker = get_ticker(symbol)
        if not ticker:
            raise RuntimeError(f"[STABILITY_METRICS] {symbol}: cannot fetch yfinance ticker data")

        try:
            info = ticker.info

            # Validate 'beta' field exists explicitly (not using .get() default)
            if "beta" not in info:
                raise RuntimeError(f"[STABILITY_METRICS] {symbol}: beta field missing from yfinance data")

            beta_raw = info["beta"]

            # Validate value is not None
            if beta_raw is None:
                raise RuntimeError(f"[STABILITY_METRICS] {symbol}: beta field is None (unavailable from yfinance)")

            # Convert to float and validate
            beta = float(beta_raw)

            # Reject extreme values that indicate data corruption
            if abs(beta) > 200:
                raise RuntimeError(
                    f"[STABILITY_METRICS] {symbol}: extreme beta value {beta} (out of range [-200, 200]). "
                    f"Data appears corrupted."
                )

            return beta
        except RuntimeError:
            raise
        except (ValueError, TypeError) as e:
            raise RuntimeError(f"[STABILITY_METRICS] {symbol}: failed to parse beta ({type(e).__name__}: {e})") from e
        except ZeroDivisionError as e:
            raise RuntimeError(f"[STABILITY_METRICS] {symbol}: division error parsing beta: {e}") from e

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
