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
            # CRITICAL (Session 275+): Only use SEC-audited market cap.
            # Removed yfinance_snapshot fallback - if SEC data unavailable, market cap is unavailable.
            # No silent fallbacks: governance requires explicit data_unavailable flags.
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

            # No SEC data available - fail-fast with explicit unavailable marker
            return [{
                "symbol": symbol,
                "market_cap": None,
                "shares_outstanding": None,
                "data_source": None,
                "data_unavailable": True,
                "reason": "sec_data_unavailable",
                "computed_at": now_et
            }]

def main() -> int:
    return run_loader(MarketCapComputedLoader)
if __name__ == "__main__":
    sys.exit(main())
