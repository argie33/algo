#!/usr/bin/env python3
import sys
"""
Earnings History Loader - Optimal Pattern.

Loads historical earnings dates and actual EPS.
Inherits watermarks, dedup, multi-source routing, parallelism, and bulk COPY.

Run:
    python3 loadearningshistory.py [--symbols AAPL,MSFT] [--parallelism 8]
"""
from loaders.loader_helper import setup_imports
setup_imports()

import logging

import argparse
from utils.loader_helpers import get_active_symbols
logger = logging.getLogger(__name__)
import os
from datetime import date
from typing import List, Optional

from utils.optimal_loader import OptimalLoader
from utils.loader_config import get_parallelism, get_default_parallelism

class EarningsHistoryLoader(OptimalLoader):
    table_name = "earnings_history"
    primary_key = ("symbol", "quarter")
    watermark_field = "earnings_date"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch earnings history from yfinance earnings_dates."""
        try:
            from utils.yfinance_wrapper import get_ticker
            from datetime import datetime
            yf_symbol = symbol.replace(".", "-") if "." in symbol else symbol
            ticker = get_ticker(yf_symbol)
            df = ticker.earnings_dates
            if df is None or (hasattr(df, "empty") and df.empty):
                return []

            rows = []
            cutoff = since.isoformat() if since else "2000-01-01"
            for idx, row in df.iterrows():
                try:
                    if hasattr(idx, "date"):
                        ed = idx.date().isoformat()
                    else:
                        ed = str(idx)[:10]
                    if ed < cutoff:
                        continue
                    eps_est = row.get("EPS Estimate")
                    eps_actual = row.get("Reported EPS")
                    surprise_pct = row.get("Surprise(%)")

                    def _safe_float(v):
                        try:
                            import math
                            f = float(v)
                            return None if math.isnan(f) else round(f, 4)
                        except (TypeError, ValueError):
                            return None

                    # Derive quarter start date (the quarter in which earnings fall)
                    try:
                        dt = datetime.fromisoformat(ed)
                        q = (dt.month - 1) // 3 + 1
                        qstart_month = (q - 1) * 3 + 1
                        quarter_str = f"{dt.year}-{qstart_month:02d}-01"
                    except Exception as e:
                        logger.warning(f"Exception: {e}")
                        quarter_str = ed[:10]

                    rows.append({
                        "symbol": symbol,
                        "quarter": quarter_str,
                        "earnings_date": ed,
                        "eps_estimate": _safe_float(eps_est),
                        "eps_actual": _safe_float(eps_actual),
                        "surprise_percent": _safe_float(surprise_pct),
                    })
                except Exception as e:
                    logging.debug(f"Earnings row error {symbol} {idx}: {e}")

            # Deduplicate by (symbol, quarter) - keep most recent earnings_date
            if rows:
                seen = {}
                for row in rows:
                    key = (row["symbol"], row["quarter"])
                    if key not in seen or row["earnings_date"] > seen[key]["earnings_date"]:
                        seen[key] = row
                rows = list(seen.values())

            return rows
        except Exception as e:
            logging.debug(f"Earnings fetch error for {symbol}: {e}")
            return []

    def transform(self, rows):
        return rows

    def _validate_row(self, row: dict) -> bool:
        if not super()._validate_row(row):
            return False
        return bool(row.get("quarter")) and bool(row.get("earnings_date"))

def main():
    parser = argparse.ArgumentParser(description="Optimal earnings_history loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all from stocks table.")
    parser.add_argument("--parallelism", type=int, default=get_default_parallelism("earnings_history"), help="Concurrent workers")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = get_active_symbols(timeout_secs=60)

    loader = EarningsHistoryLoader()
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

