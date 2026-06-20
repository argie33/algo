#!/usr/bin/env python3
import sys


"""
Growth Metrics Loader - Computes multi-year growth metrics from annual financials.

Metrics: Revenue Growth (1Y, 3Y, 5Y), EPS Growth (1Y, 3Y, 5Y), Growth Score (0-100).
Requires: annual_income_statement populated.
"""

import logging
from datetime import date
from typing import Any, Optional


logger = logging.getLogger(__name__)

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.optimal_loader import OptimalLoader


class GrowthMetricsLoader(OptimalLoader):
    table_name = "growth_metrics"
    primary_key = ("symbol",)
    watermark_field = "created_at"

    def fetch_incremental(self, symbol: str, since: date | None):
        """Compute multi-year growth metrics from annual income statement."""
        try:
            with DatabaseContext("read") as cur:
                # Fetch up to 10 years of financials to calculate 1Y, 3Y, 5Y growth
                cur.execute(
                    """
                    SELECT fiscal_year, revenue, earnings_per_share
                    FROM annual_income_statement
                    WHERE symbol = %s
                    ORDER BY fiscal_year DESC
                    LIMIT 10
                """,
                    (symbol,),
                )

                rows = cur.fetchall()

                if not rows or len(rows) < 1:
                    return None

                # Sort by year ascending for easier calculation
                rows = list(reversed(rows))

                latest = rows[-1]  # Most recent year
                metrics = self._compute_metrics(symbol, latest, rows)

                if metrics:
                    return [metrics]
                return None

        except Exception as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    @staticmethod
    def _compute_metrics(symbol: str, latest: tuple, all_years: list) -> dict | None:
        """Compute multi-year growth metrics."""
        _latest_year, latest_rev, latest_eps = latest

        metrics: dict[str, Any] = {"symbol": symbol}

        # Calculate 1Y, 3Y, 5Y growth rates
        for lookback in [1, 3, 5]:
            # Revenue growth
            idx = -(lookback + 1)
            if len(all_years) > lookback and all_years[idx] and latest_rev:
                _prev_year, prev_rev, _prev_eps = all_years[idx]
                if prev_rev and prev_rev > 0:
                    # Convert to float to support Decimal types from database
                    latest_rev_f = float(latest_rev)
                    prev_rev_f = float(prev_rev)
                    rev_growth = (
                        ((latest_rev_f / prev_rev_f) ** (1.0 / lookback)) - 1
                    ) * 100
                    metrics[f"revenue_growth_{lookback}y"] = float(round(rev_growth, 2))
                else:
                    metrics[f"revenue_growth_{lookback}y"] = None
            else:
                metrics[f"revenue_growth_{lookback}y"] = None

            # EPS growth
            if len(all_years) > lookback and all_years[idx] and latest_eps:
                _prev_year2, _prev_rev2, prev_eps = all_years[idx]
                if prev_eps and prev_eps > 0:
                    # Convert to float to support Decimal types from database
                    latest_eps_f = float(latest_eps)
                    prev_eps_f = float(prev_eps)
                    eps_growth = (
                        ((latest_eps_f / prev_eps_f) ** (1.0 / lookback)) - 1
                    ) * 100
                    metrics[f"eps_growth_{lookback}y"] = float(round(eps_growth, 2))
                else:
                    metrics[f"eps_growth_{lookback}y"] = None
            else:
                metrics[f"eps_growth_{lookback}y"] = None

        return metrics

    def transform(self, rows):
        """No transformation needed; metrics already computed."""
        return rows



if __name__ == "__main__":
    sys.exit(run_loader(GrowthMetricsLoader))
