#!/usr/bin/env python3
import logging, sys
from datetime import date, datetime, timedelta
from typing import Any
from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.optimal_loader import OptimalLoader

class PriceExtremesLoader(OptimalLoader):
    table_name = "price_extremes_52week"
    primary_key = ("symbol",)
    watermark_field = "computed_at"
    exclude_etfs_from_symbols = True
    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        from utils.infrastructure.timezone import EASTERN_TZ
        now_et = datetime.now(EASTERN_TZ)
        lookback_date = now_et.date() - timedelta(days=365)
        with DatabaseContext("read") as cur:
            cur.execute("SELECT MAX(high), MIN(low), COUNT(*), MAX(date) FROM price_daily WHERE symbol = %s AND date >= %s", (symbol, lookback_date))
            row = cur.fetchone()
        if not row or row[0] is None:
            return [{"symbol": symbol, "fifty_two_week_high": None, "fifty_two_week_low": None, "data_unavailable": True, "reason": "no_data", "computed_at": now_et}]
        return [{"symbol": symbol, "fifty_two_week_high": row[0], "fifty_two_week_low": row[1], "bar_count": row[2], "data_unavailable": False, "computed_at": now_et}]

def main() -> int:
    return run_loader(PriceExtremesLoader)
if __name__ == "__main__":
    sys.exit(main())
