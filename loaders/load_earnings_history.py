#!/usr/bin/env python3
import sys


"""
Earnings History Loader - Optimal Pattern.

Loads historical earnings dates and actual EPS.
Inherits watermarks, dedup, multi-source routing, parallelism, and bulk COPY.

Run:
    python3 loadearningshistory.py [--symbols AAPL,MSFT] [--parallelism 8]
"""

import logging


logger = logging.getLogger(__name__)
from datetime import date
from typing import Optional

from loaders.runner import run_loader
from utils.optimal_loader import OptimalLoader


class EarningsHistoryLoader(OptimalLoader):
    table_name = "earnings_history"
    primary_key = ("symbol", "quarter")
    watermark_field = "earnings_date"

    def fetch_incremental(self, symbol: str, since: date | None):
        """Fetch earnings history from yfinance earnings_dates."""
        try:
            from datetime import datetime

            from utils.external.yfinance import get_ticker

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

                    def _float(v):
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
                    except (ValueError, ZeroDivisionError, TypeError) as e:
                        logger.warning(f"Exception: {e}")
                        quarter_str = ed[:10]

                    rows.append(
                        {
                            "symbol": symbol,
                            "quarter": quarter_str,
                            "earnings_date": ed,
                            "eps_estimate": _float(eps_est),
                            "eps_actual": _float(eps_actual),
                            "surprise_percent": _float(surprise_pct),
                        }
                    )
                except (ValueError, ZeroDivisionError, TypeError) as e:
                    logging.debug(f"Earnings row error {symbol} {idx}: {e}")

            # Deduplicate by (symbol, quarter) - keep most recent earnings_date
            if rows:
                seen: dict[tuple[str, str], dict] = {}
                for row in rows:
                    key = (row["symbol"], row["quarter"])
                    if (
                        key not in seen
                        or row["earnings_date"] > seen[key]["earnings_date"]
                    ):
                        seen[key] = row
                rows = list(seen.values())

            return rows
        except (ValueError, ZeroDivisionError, TypeError) as e:
            error_msg = f"Failed to fetch earnings history for {symbol}: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def transform(self, rows):
        return rows

    def _validate_row(self, row: dict) -> bool:
        if not super()._validate_row(row):
            return False
        return bool(row.get("quarter")) and bool(row.get("earnings_date"))



if __name__ == "__main__":
    sys.exit(run_loader(EarningsHistoryLoader))
