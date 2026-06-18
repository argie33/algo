#!/usr/bin/env python3
import sys


"""
Growth Metrics Loader - Computes multi-year growth metrics from annual financials.

Metrics: Revenue Growth (1Y, 3Y, 5Y), EPS Growth (1Y, 3Y, 5Y), Growth Score (0-100).
Requires: annual_income_statement populated.
"""

import argparse
import logging
from datetime import date
from typing import Optional


logger = logging.getLogger(__name__)

from utils.db.context import DatabaseContext
from utils.loaders.config import get_default_parallelism
from utils.loaders.helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader


class GrowthMetricsLoader(OptimalLoader):
    table_name = "growth_metrics"
    primary_key = ("symbol",)
    watermark_field = "created_at"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
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
            logger.debug(f"Error computing growth metrics for {symbol}: {e}")
            return None

    @staticmethod
    def _compute_metrics(symbol: str, latest: tuple, all_years: list) -> Optional[dict]:
        """Compute multi-year growth metrics."""
        latest_year, latest_rev, latest_eps = latest

        metrics = {"symbol": symbol}

        # Calculate 1Y, 3Y, 5Y growth rates
        for lookback in [1, 3, 5]:
            # Revenue growth
            idx = -(lookback + 1)
            if len(all_years) > lookback and all_years[idx] and latest_rev:
                prev_year, prev_rev, prev_eps = all_years[idx]
                if prev_rev and prev_rev > 0:
                    rev_growth = (
                        ((latest_rev / prev_rev) ** (1.0 / lookback)) - 1
                    ) * 100
                    metrics[f"revenue_growth_{lookback}y"] = float(round(rev_growth, 2))
                else:
                    metrics[f"revenue_growth_{lookback}y"] = None
            else:
                metrics[f"revenue_growth_{lookback}y"] = None

            # EPS growth
            if len(all_years) > lookback and all_years[idx] and latest_eps:
                prev_year, prev_rev, prev_eps = all_years[idx]
                if prev_eps and prev_eps > 0:
                    eps_growth = (
                        ((latest_eps / prev_eps) ** (1.0 / lookback)) - 1
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


def main():
    parser = argparse.ArgumentParser(description="Growth metrics loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all.")
    parser.add_argument(
        "--parallelism", type=int, default=get_default_parallelism("growth_metrics")
    )
    args = parser.parse_args()

    symbols = (
        [s.strip().upper() for s in args.symbols.split(",")]
        if args.symbols
        else get_active_symbols(timeout_secs=60)
    )

    loader = GrowthMetricsLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    fail_rate = stats.get("symbols_failed", 0) / max(len(symbols), 1)
    if fail_rate > 0.05:
        logger.error(
            f"Too many failures: {stats['symbols_failed']}/{len(symbols)} ({fail_rate*100:.1f}%)"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
