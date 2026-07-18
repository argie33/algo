#!/usr/bin/env python3
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
            cur.execute("SELECT close FROM price_daily WHERE symbol = %s ORDER BY date DESC LIMIT 1", (symbol,))
            price_row = cur.fetchone()
            if not price_row or price_row[0] is None:
                return [{"symbol": symbol, "market_cap": None, "data_unavailable": True, "reason": "no_price", "computed_at": now_et}]
            latest_price = safe_float(price_row[0], "close")
            cur.execute("SELECT shares_outstanding FROM sec_valuations WHERE symbol = %s ORDER BY computed_at DESC LIMIT 1", (symbol,))
            shares_row = cur.fetchone()
            if not shares_row or shares_row[0] is None:
                return [{"symbol": symbol, "market_cap": None, "data_unavailable": True, "reason": "no_shares", "computed_at": now_et}]
            shares = safe_float(shares_row[0], "shares_outstanding")
            if latest_price and shares and latest_price > 0 and shares > 0:
                return [{"symbol": symbol, "market_cap": latest_price * shares, "latest_price": latest_price, "shares_outstanding": shares, "data_unavailable": False, "computed_at": now_et}]
            return [{"symbol": symbol, "market_cap": None, "data_unavailable": True, "reason": "invalid", "computed_at": now_et}]

def main() -> int:
    return run_loader(MarketCapComputedLoader)
if __name__ == "__main__":
    sys.exit(main())
