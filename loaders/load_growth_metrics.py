#!/usr/bin/env python3
"""
Growth Metrics Loader - Computes multi-year growth metrics from annual financials.

Metrics: Revenue Growth (1Y, 3Y, 5Y), EPS Growth (1Y, 3Y, 5Y), Growth Score (0-100).
Requires: annual_income_statement populated.
"""

import logging
import sys
from datetime import date
from typing import Any

import psycopg2

from loaders.runner import run_loader
from utils.loaders import execute_query
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class GrowthMetricsLoader(OptimalLoader):
    """Growth metrics loader for real stocks only (not ETFs/bonds).

    Growth metrics are computed from annual income statement data, which is only available
    for companies that file with the SEC. ETFs and bonds don't have financial statements.
    """

    table_name = "growth_metrics"
    primary_key = ("symbol",)
    watermark_field = "created_at"
    exclude_etfs_from_symbols = True

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]] | None:
        """Compute multi-year growth metrics from annual income statement.

        Returns record with data_unavailable marker if financial data unavailable (normal for small caps, new IPOs).
        Growth metrics are optional enrichment; their absence does not prevent trading.
        But unavailability should be explicit (data_unavailable flag), not silent skips.
        """
        try:
            # Fetch up to 10 years of financials to calculate 1Y, 3Y, 5Y growth
            rows = execute_query(
                """
                SELECT fiscal_year, revenue, earnings_per_share
                FROM annual_income_statement
                WHERE symbol = %s
                ORDER BY fiscal_year DESC
                LIMIT 10
            """,
                (symbol,),
            )

            if not rows or len(rows) < 1:
                logger.info(
                    f"[GROWTH_METRICS] No annual income statement data for {symbol} (new stock/no financials yet)"
                )
                return [
                    {
                        "symbol": symbol,
                        "revenue_growth_1y": None,
                        "revenue_growth_3y": None,
                        "revenue_growth_5y": None,
                        "eps_growth_1y": None,
                        "eps_growth_3y": None,
                        "eps_growth_5y": None,
                        "data_unavailable": True,
                        "reason": "No annual income statement data available",
                    }
                ]

            # Sort by year ascending for easier calculation
            rows_list = list(reversed(rows))

            latest = rows_list[-1]  # Most recent year
            metrics = self._compute_metrics(symbol, latest, rows_list)

            if not metrics:
                logger.warning(f"[GROWTH_METRICS] Failed to compute metrics for {symbol} (calculation error)")
                return [
                    {
                        "symbol": symbol,
                        "revenue_growth_1y": None,
                        "revenue_growth_3y": None,
                        "revenue_growth_5y": None,
                        "eps_growth_1y": None,
                        "eps_growth_3y": None,
                        "eps_growth_5y": None,
                        "data_unavailable": True,
                        "reason": "Metrics computation failed",
                    }
                ]
            return [metrics]

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"[GROWTH_METRICS] Database error for {symbol}: {e}")
            raise RuntimeError(
                f"[GROWTH_METRICS] Database error fetching financials for {symbol}: {e}. "
                f"Cannot compute growth metrics without access to financial data."
            ) from e

    @staticmethod
    def _compute_metrics(symbol: str, latest: tuple[Any, Any, Any], all_years: list[Any]) -> dict[str, Any] | None:
        """Compute multi-year growth metrics.

        Args:
            symbol: Stock symbol
            latest: Tuple of (fiscal_year, revenue, earnings_per_share) for most recent year
            all_years: List of all historical year tuples, sorted ascending (oldest first)

        Returns:
            Dictionary with computed growth metrics and data_unavailable flag.
            Raises ValueError if inputs are malformed (fail-fast on data corruption).
        """
        if not latest or len(latest) != 3:
            raise ValueError(
                f"[GROWTH_METRICS] Malformed latest data for {symbol}: expected (year, revenue, eps), got {latest}"
            )
        if not all_years or not isinstance(all_years, list):
            raise ValueError(f"[GROWTH_METRICS] Malformed all_years for {symbol}: expected list, got {type(all_years)}")

        _latest_year, latest_rev, latest_eps = latest

        metrics: dict[str, Any] = {"symbol": symbol}

        # Calculate 1Y, 3Y, 5Y growth rates
        for lookback in [1, 3, 5]:
            # Revenue growth
            idx = -(lookback + 1)
            if len(all_years) > lookback and all_years[idx] and latest_rev:
                _prev_year, prev_rev, _prev_eps = all_years[idx]
                try:
                    if prev_rev is not None and float(prev_rev) > 0 and float(latest_rev) > 0:
                        # Convert to float to support Decimal types from database
                        latest_rev_f = float(latest_rev)
                        prev_rev_f = float(prev_rev)
                        rev_growth = (((latest_rev_f / prev_rev_f) ** (1.0 / lookback)) - 1) * 100
                        metrics[f"revenue_growth_{lookback}y"] = float(round(rev_growth, 2))
                    else:
                        metrics[f"revenue_growth_{lookback}y"] = None
                except (TypeError, ValueError):
                    metrics[f"revenue_growth_{lookback}y"] = None
            else:
                metrics[f"revenue_growth_{lookback}y"] = None

            # EPS growth
            if len(all_years) > lookback and all_years[idx] and latest_eps:
                _prev_year, _prev_rev, prev_eps = all_years[idx]
                try:
                    if prev_eps is not None and float(prev_eps) > 0 and float(latest_eps) > 0:
                        # Convert to float to support Decimal types from database
                        latest_eps_f = float(latest_eps)
                        prev_eps_f = float(prev_eps)
                        eps_growth = (((latest_eps_f / prev_eps_f) ** (1.0 / lookback)) - 1) * 100
                        metrics[f"eps_growth_{lookback}y"] = float(round(eps_growth, 2))
                    else:
                        metrics[f"eps_growth_{lookback}y"] = None
                except (TypeError, ValueError):
                    metrics[f"eps_growth_{lookback}y"] = None
            else:
                metrics[f"eps_growth_{lookback}y"] = None

        # Check if we actually have any real data (not all NULL)
        # Explicitly check that computed growth metrics exist and are not None
        has_revenue_growth = any(metrics.get(f"revenue_growth_{y}y") is not None for y in [1, 3, 5])
        has_eps_growth = any(metrics.get(f"eps_growth_{y}y") is not None for y in [1, 3, 5])

        if has_revenue_growth or has_eps_growth:
            metrics["data_unavailable"] = False
        else:
            # All growth metrics are NULL - mark as unavailable
            metrics["data_unavailable"] = True
            metrics["reason"] = "Insufficient historical data to compute growth rates"

        metrics["updated_at"] = date.today().isoformat()

        return metrics

    def transform(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """No transformation needed; metrics already computed."""
        return rows


if __name__ == "__main__":
    sys.exit(run_loader(GrowthMetricsLoader))
