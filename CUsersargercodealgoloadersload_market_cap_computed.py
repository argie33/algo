#!/usr/bin/env python3
"""Market Cap Loader - Compute from shares outstanding + latest price.

QUICK WIN (Session 234):
Replaces yfinance market_cap (~3% of yfinance_snapshot) with SQL computation.

Market Cap = Latest Price × Shares Outstanding (from SEC)

Benefits:
- Always current (uses latest daily price)
- More accurate than yfinance (SEC shares outstanding > yfinance estimates)
- No external API needed (uses existing price_daily + sec_valuations data)

Run:
    python3 loaders/load_market_cap_computed.py [--symbols AAPL,MSFT] [--parallelism 4]
"""

import logging
import sys
from datetime import date, datetime
from typing import Any

from loaders.runner import run_loader
from loaders.timeout_config import configure_socket_timeout
from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ
from utils.optimal_loader import OptimalLoader
from utils.type_conversion import safe_float

logger = logging.getLogger(__name__)

# Configure socket timeout to prevent indefinite hangs
configure_socket_timeout(30)


class MarketCapComputedLoader(OptimalLoader):
    """Compute market cap from shares outstanding + latest price.

    QUICK WIN: Eliminates yfinance market_cap dependency (~3% of yfinance load).
    Computation uses SEC shares_outstanding + latest price from price_daily.

    Benefits:
    - Always current (latest price + recent SEC data)
    - More accurate than yfinance (SEC audited shares > yfinance estimates)
    - No external API call required
    """

    table_name = "market_cap_computed"
    primary_key = ("symbol",)
    watermark_field = "computed_at"
    exclude_etfs_from_symbols = True

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Compute market cap = latest_price × shares_outstanding.

        Returns:
            List with single market cap dict or data_unavailable marker
        """
        now_et = datetime.now(EASTERN_TZ)

        try:
            with DatabaseContext("read") as cur:
                # Get latest price from price_daily
                cur.execute(
                    "SELECT close FROM price_daily WHERE symbol = %s ORDER BY date DESC LIMIT 1",
                    (symbol,),
                )
                price_row = cur.fetchone()

                if not price_row or price_row[0] is None:
                    return [
                        {
                            "symbol": symbol,
                            "market_cap": None,
                            "latest_price": None,
                            "shares_outstanding": None,
                            "data_unavailable": True,
                            "reason": "no_latest_price",
                            "computed_at": now_et,
                        }
                    ]

                latest_price = safe_float(price_row[0])

                # Get shares outstanding from sec_valuations (most recent)
                cur.execute(
                    "SELECT shares_outstanding FROM sec_valuations WHERE symbol = %s ORDER BY computed_at DESC LIMIT 1",
                    (symbol,),
                )
                shares_row = cur.fetchone()

                if not shares_row or shares_row[0] is None:
                    return [
                        {
                            "symbol": symbol,
                            "market_cap": None,
                            "latest_price": latest_price,
                            "shares_outstanding": None,
                            "data_unavailable": True,
                            "reason": "no_shares_outstanding",
                            "computed_at": now_et,
                        }
                    ]

                shares_outstanding = safe_float(shares_row[0])

                if latest_price is None or shares_outstanding is None or latest_price <= 0 or shares_outstanding <= 0:
                    return [
                        {
                            "symbol": symbol,
                            "market_cap": None,
                            "latest_price": latest_price,
                            "shares_outstanding": shares_outstanding,
                            "data_unavailable": True,
                            "reason": "invalid_price_or_shares",
                            "computed_at": now_et,
                        }
                    ]

                market_cap = latest_price * shares_outstanding

                return [
                    {
                        "symbol": symbol,
                        "market_cap": market_cap,
                        "latest_price": latest_price,
                        "shares_outstanding": shares_outstanding,
                        "data_unavailable": False,
                        "reason": None,
                        "computed_at": now_et,
                    }
                ]

        except Exception as e:
            logger.error(f"[MARKET_CAP] Error computing for {symbol}: {e}")
            return [
                {
                    "symbol": symbol,
                    "market_cap": None,
                    "latest_price": None,
                    "shares_outstanding": None,
                    "data_unavailable": True,
                    "reason": f"compute_error:{type(e).__name__}",
                    "computed_at": now_et,
                }
            ]


def main() -> int:
    """Entry point for load_market_cap_computed.py."""
    try:
        return run_loader(MarketCapComputedLoader)
    except Exception as e:
        logger.error(f"[MARKET_CAP FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        try:
            symbols = set()
            with DatabaseContext("read") as cur:
                cur.execute("SELECT DISTINCT symbol FROM stock_symbols WHERE active = TRUE")
                symbols = {row[0] for row in cur.fetchall()}

            with DatabaseContext("write") as cur:
                for symbol in symbols:
                    cur.execute(
                        """
                        INSERT INTO market_cap_computed (symbol, data_unavailable, reason, computed_at)
                        VALUES (%s, TRUE, %s, NOW())
                        ON CONFLICT (symbol) DO NOTHING
                        """,
                        (symbol, f"loader_crash:{type(e).__name__}"),
                    )
        except Exception as mark_err:
            logger.error(f"[MARKET_CAP] Failed to mark data unavailable: {mark_err}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
