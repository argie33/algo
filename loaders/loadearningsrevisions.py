#!/usr/bin/env python3
"""Earnings Estimate Revisions Loader — up/down analyst revision counts from yfinance.

Table: earnings_estimate_revisions
Primary key: (symbol, quarter, fiscal_year, revision_type)

Run: python3 loaders/loadearningsrevisions.py [--symbols AAPL,MSFT] [--parallelism 4]
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import logging
from datetime import date
from typing import List, Optional

from utils.yfinance_wrapper import get_ticker

from config.env_loader import load_env
from utils.loader_helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader

log = logging.getLogger(__name__)

class EarningsRevisionsLoader(OptimalLoader):
    table_name = "earnings_estimate_revisions"
    primary_key = ("symbol", "quarter", "fiscal_year", "revision_type")
    watermark_field = None  # Full refresh each run

    def fetch_incremental(self, symbol: str, since: Optional[date]) -> Optional[List[dict]]:
        try:
            yf_symbol = symbol.replace(".", "-") if "." in symbol else symbol
            ticker = get_ticker(yf_symbol)

            eps_revisions = ticker.eps_revisions
            if eps_revisions is None or (hasattr(eps_revisions, "empty") and eps_revisions.empty):
                return None

            rows = []
            current_fy = date.today().year
            today = date.today().isoformat()

            for col in eps_revisions.columns:
                col_str = str(col)
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

                for revision_type in ("up", "down"):
                    idx_key = "upLast30days" if revision_type == "up" else "downLast30days"
                    try:
                        val = eps_revisions.loc[idx_key, col] if idx_key in eps_revisions.index else None
                        if val is None:
                            continue
                        count = int(float(val))
                    except (TypeError, ValueError, KeyError):
                        count = 0

                    est_before = None
                    est_after = None
                    try:
                        eb = eps_revisions.loc["upLast7days", col] if "upLast7days" in eps_revisions.index else None
                        est_before = float(eb) if eb is not None else None
                    except Exception:
                        pass

                    rows.append({
                        "symbol": symbol,
                        "quarter": quarter,
                        "fiscal_year": fiscal_year,
                        "revision_date": today,
                        "estimate_before": est_before,
                        "estimate_after": None,
                        "revision_type": revision_type,
                    })

            return rows if rows else None

        except Exception as e:
            log.debug("Earnings revisions error for %s: %s", symbol, e)
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

    loader = EarningsRevisionsLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    fail_rate = stats.get("symbols_failed", 0) / max(len(symbols), 1)
    if fail_rate > 0.05:
        log.error(f"Too many failures: {stats['symbols_failed']}/{len(symbols)} ({fail_rate*100:.1f}%)")
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
