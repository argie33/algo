#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

"""
Earnings History Loader - Optimal Pattern.

Loads historical earnings dates and actual EPS.
Inherits watermarks, dedup, multi-source routing, parallelism, and bulk COPY.

Run:
    python3 loadearningshistory.py [--symbols AAPL,MSFT] [--parallelism 8]
"""
from utils.structured_logger import get_logger

import argparse
from utils.loader_helpers import get_active_symbols
import logging
logger = get_logger(__name__)
import os
from config.env_loader import load_env
from datetime import date
from typing import List, Optional

from utils.optimal_loader import OptimalLoader




class EarningsHistoryLoader(OptimalLoader):
    table_name = "earnings_history"
    primary_key = ("symbol", "earnings_date")
    watermark_field = "earnings_date"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch earnings history from yfinance earnings_dates."""
        try:
            import yfinance as yf
            from datetime import datetime
            yf_symbol = symbol.replace(".", "-") if "." in symbol else symbol
            ticker = yf.Ticker(yf_symbol)
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

                    rows.append({
                        "symbol": symbol,
                        "earnings_date": ed,
                        "eps_estimate": _safe_float(eps_est),
                        "eps_actual": _safe_float(eps_actual),
                        "surprise_percent": _safe_float(surprise_pct),
                    })
                except Exception as e:
                    logging.debug(f"Earnings row error {symbol} {idx}: {e}")
            return rows
        except Exception as e:
            logging.debug(f"Earnings fetch error for {symbol}: {e}")
            return []

    def transform(self, rows):
        return rows

    def _validate_row(self, row: dict) -> bool:
        if not super()._validate_row(row):
            return False
        ed = row.get("earnings_date")
        if not ed:
            return False
        try:
            year = int(str(ed)[:4])
            return 1990 < year < 2100
        except (TypeError, ValueError):
            return False



def main():
    load_env()
    parser = argparse.ArgumentParser(description="Optimal earnings_history loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all from stocks table.")
    parser.add_argument("--parallelism", type=int, default=8, help="Concurrent workers")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = get_active_symbols()

    loader = EarningsHistoryLoader()
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

