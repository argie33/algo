#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

"""
Earnings Estimate Trends Loader.

Fetches EPS estimate trend data (current vs prior period estimates) from yfinance
and stores in earnings_estimate_trends table.

Run:
    python3 loadearningsestimates.py [--parallelism 4]
"""

import argparse
import logging
from datetime import date, timedelta
from typing import List, Optional

from config.env_loader import load_env
from utils.loader_helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader

log = logging.getLogger(__name__)


def _period_quarter_date(period: str) -> str:
    """Approximate quarter date for the period label."""
    today = date.today()
    if "Q" in period:
        offset = 91 if period.startswith("+") else 0
    else:
        offset = 365 if period.startswith("+") else 0
    return str(today + timedelta(days=offset))


class EarningsEstimatesLoader(OptimalLoader):
    table_name = "earnings_estimate_trends"
    primary_key = ("symbol", "quarter", "period")
    watermark_field = "quarter"

    def fetch_incremental(self, symbol: str, since: Optional[date]) -> Optional[List[dict]]:
        """Fetch EPS trend data from yfinance."""
        try:
            df = self.router.fetch_eps_trend(symbol)
        except Exception as e:
            log.debug("eps_trend failed for %s: %s", symbol, e)
            return None

        if df is None or (hasattr(df, 'empty') and df.empty):
            return None

        rows = []
        today = date.today()
        try:
            for period in df.columns if hasattr(df, 'columns') else []:
                col = df[period]
                quarter_dt = _period_quarter_date(str(period))
                fiscal_year = today.year

                current_est = None
                prior_est = None
                try:
                    current_est = float(col.get("current") or 0) if hasattr(col, 'get') else float(col.iloc[col.index.get_loc("current")])
                except Exception:
                    pass
                try:
                    prior_est = float(col.get("30daysAgo") or 0) if hasattr(col, 'get') else float(col.iloc[col.index.get_loc("30daysAgo")])
                except Exception:
                    pass

                change = None
                if current_est is not None and prior_est is not None and prior_est != 0:
                    change = round(current_est - prior_est, 4)

                rows.append({
                    "symbol": symbol,
                    "quarter": quarter_dt,
                    "fiscal_year": fiscal_year,
                    "period": str(period),
                    "current_estimate": current_est,
                    "prior_estimate": prior_est,
                    "change_estimate": change,
                })
        except Exception as e:
            log.debug("eps_trend parse error for %s: %s", symbol, e)
            return None

        return rows or None


def main() -> int:
    load_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("--parallelism", type=int, default=4)
    args = parser.parse_args()

    symbols = get_active_symbols()
    loader = EarningsEstimatesLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    log.info("Earnings estimates load complete: %s", stats)
    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
