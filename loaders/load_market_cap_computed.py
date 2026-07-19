#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
from datetime import date, datetime
from typing import Any

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.optimal_loader import OptimalLoader
from utils.type_conversion import safe_float


class MarketCapComputedLoader(OptimalLoader):
    table_name = "market_cap_computed"
    primary_key = ("symbol",)
    watermark_field = "computed_at"
    exclude_etfs_from_symbols = True
    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        from utils.infrastructure.timezone import EASTERN_TZ
        now_et = datetime.now(EASTERN_TZ)
        with DatabaseContext("read") as cur:
            # Try SEC-computed market cap first (price × shares from audited SEC data)
            cur.execute("SELECT market_cap, shares_outstanding FROM sec_valuations WHERE symbol = %s AND NOT data_unavailable ORDER BY computed_at DESC LIMIT 1", (symbol,))
            sec_row = cur.fetchone()
            if sec_row and sec_row[0] is not None:
                market_cap = safe_float(sec_row[0], "market_cap")
                shares = safe_float(sec_row[1], "shares_outstanding")
                return [{
                    "symbol": symbol,
                    "market_cap": market_cap,
                    "shares_outstanding": int(shares) if shares else None,
                    "data_source": "sec_audited",
                    "data_unavailable": False,
                    "reason": None,
                    "computed_at": now_et
                }]

            # Fallback to yfinance market_cap when SEC data unavailable (authoritative real data)
            cur.execute("SELECT market_cap FROM yfinance_snapshot WHERE symbol = %s AND data_available ORDER BY fetched_at DESC LIMIT 1", (symbol,))
            yf_row = cur.fetchone()
            if yf_row and yf_row[0] is not None:
                market_cap = safe_float(yf_row[0], "market_cap")
                return [{
                    "symbol": symbol,
                    "market_cap": market_cap,
                    "shares_outstanding": None,
                    "data_source": "yfinance",
                    "data_unavailable": False,
                    "reason": None,
                    "computed_at": now_et
                }]

            # No data available from either source
            return [{
                "symbol": symbol,
                "market_cap": None,
                "shares_outstanding": None,
                "data_source": None,
                "data_unavailable": True,
                "reason": "no_market_cap_data",
                "computed_at": now_et
            }]

def main() -> int:
    return run_loader(MarketCapComputedLoader)
if __name__ == "__main__":
    sys.exit(main())
