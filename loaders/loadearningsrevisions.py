#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

"""
Earnings Estimate Revisions Loader.

Fetches EPS revision data (up/down revision counts by period) from yfinance
and stores in earnings_estimate_revisions table.

Run:
    python3 loadearningsrevisions.py [--parallelism 4]
"""

import argparse
import logging
from datetime import date, timedelta
from typing import List, Optional

from config.env_loader import load_env
from utils.loader_helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader

log = logging.getLogger(__name__)

# Map from period label to approximate future quarter date
_PERIOD_TO_OFFSET = {"0Q": 0, "+1Q": 1, "0Y": 0, "+1Y": 1}


def _period_to_date(period: str) -> str:
    """Approximate date for revision record."""
    today = date.today()
    if "Q" in period:
        offset = _PERIOD_TO_OFFSET.get(period, 0) * 91
    else:
        offset = _PERIOD_TO_OFFSET.get(period, 0) * 365
    return str(today + timedelta(days=offset))


class EarningsRevisionsLoader(OptimalLoader):
    table_name = "earnings_estimate_revisions"
    primary_key = ("symbol", "quarter", "revision_type")
    watermark_field = "quarter"

    def fetch_incremental(self, symbol: str, since: Optional[date]) -> Optional[List[dict]]:
        """Fetch EPS revision counts from yfinance."""
        try:
            df = self.router.fetch_eps_revisions(symbol)
        except Exception as e:
            log.debug("eps_revisions failed for %s: %s", symbol, e)
            return None

        if df is None or (hasattr(df, 'empty') and df.empty):
            return None

        rows = []
        today = date.today()
        try:
            for period in df.index:
                row = df.loc[period]
                # Create an "up" record and a "down" record per period
                quarter_dt = _period_to_date(str(period))
                fiscal_year = today.year

                up_count = int(row.get("upLast30days", 0) or 0)
                down_count = int(row.get("downLast30days", 0) or 0)
                current_est = float(row.get("current", 0) or 0) if hasattr(row, 'get') else 0
                prior_est = float(row.get("30daysAgo", 0) or 0) if hasattr(row, 'get') else 0

                if up_count > 0:
                    rows.append({
                        "symbol": symbol,
                        "quarter": quarter_dt,
                        "fiscal_year": fiscal_year,
                        "revision_date": str(today),
                        "estimate_before": prior_est,
                        "estimate_after": current_est,
                        "revision_type": "up",
                    })
                if down_count > 0:
                    rows.append({
                        "symbol": symbol,
                        "quarter": quarter_dt,
                        "fiscal_year": fiscal_year,
                        "revision_date": str(today),
                        "estimate_before": prior_est,
                        "estimate_after": current_est,
                        "revision_type": "down",
                    })
        except Exception as e:
            log.debug("eps_revisions parse error for %s: %s", symbol, e)
            return None

        return rows or None


def main() -> int:
    load_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("--parallelism", type=int, default=4)
    args = parser.parse_args()

    symbols = get_active_symbols()
    loader = EarningsRevisionsLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    log.info("Earnings revisions load complete: %s", stats)
    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
