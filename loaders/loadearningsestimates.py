#!/usr/bin/env python3
"""Earnings Estimates Trend Loader — EPS estimate trends from yfinance.

Shows how estimates have changed over time (current vs 30/60/90 days ago).
Table: earnings_estimate_trends
Primary key: (symbol, quarter, fiscal_year, period)

Run: python3 loaders/loadearningsestimates.py [--symbols AAPL,MSFT] [--parallelism 4]
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import logging
from datetime import date
from typing import List, Optional

from config.env_loader import load_env
from utils.loader_helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader
from utils.yfinance_wrapper import get_ticker

log = logging.getLogger(__name__)


class EarningsEstimatesLoader(OptimalLoader):
    table_name = "earnings_estimate_trends"
    primary_key = ("symbol", "quarter", "fiscal_year", "period")
    watermark_field = None  # Full refresh each run

    def fetch_incremental(self, symbol: str, since: Optional[date]) -> Optional[List[dict]]:
        try:
            yf_symbol = symbol.replace(".", "-") if "." in symbol else symbol
            ticker = get_ticker(yf_symbol)
            if not ticker:
                return None

            eps_trend = ticker.eps_trend
            if eps_trend is None or (hasattr(eps_trend, "empty") and eps_trend.empty):
                return None

            rows = []
            # eps_trend columns: 0q, +1q, 0y, +1y
            # eps_trend index: current, 7daysAgo, 30daysAgo, 60daysAgo, 90daysAgo
            current_fy = date.today().year

            for col in eps_trend.columns:
                col_str = str(col)
                # Map column to quarter label
                if col_str == "0q":
                    quarter, fiscal_year = "Q_current", current_fy
                elif col_str == "+1q":
                    quarter, fiscal_year = "Q_next", current_fy
                elif col_str == "0y":
                    quarter, fiscal_year = "FY_current", current_fy
                elif col_str == "+1y":
                    quarter, fiscal_year = "FY_next", current_fy + 1
                else:
                    quarter, fiscal_year = col_str, current_fy

                current_est = None
                prior_est = None
                change_est = None

                for idx_label in eps_trend.index:
                    period = str(idx_label)
                    try:
                        val = eps_trend.loc[idx_label, col]
                        if val is None:
                            continue
                        est = float(val)
                    except (TypeError, ValueError, KeyError):
                        continue

                    if period == "current":
                        current_est = est
                    elif period == "30daysAgo":
                        prior_est = est

                if current_est is not None and prior_est is not None:
                    change_est = round(current_est - prior_est, 4)

                rows.append({
                    "symbol": symbol,
                    "quarter": quarter,
                    "fiscal_year": fiscal_year,
                    "period": "annual" if "y" in str(col) else "quarterly",
                    "current_estimate": current_est,
                    "prior_estimate": prior_est,
                    "change_estimate": change_est,
                })

            return [r for r in rows if r.get("current_estimate") is not None] or None

        except Exception as e:
            log.debug("Earnings estimates error for %s: %s", symbol, e)
            return None

    def transform(self, rows):
        return rows

    def _get_or_create_watermark(self, symbol: str) -> Optional[date]:
        return None

    def _save_watermark(self, symbol: str, new_watermark) -> None:
        pass


def main() -> int:
    load_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", help="Comma-separated symbols")
    parser.add_argument("--parallelism", type=int, default=4)
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else get_active_symbols()

    loader = EarningsEstimatesLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    fail_rate = stats.get("symbols_failed", 0) / max(len(symbols), 1)
        if fail_rate > 0.05:
            logger.error(f"Too many failures: {stats['symbols_failed']}/{len(symbols)} ({fail_rate*100:.1f}%)")
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(main())
