#!/usr/bin/env python3
"""Insider Holdings Loader - SEC Form 4/5 (Near Real-Time).

PHASE 2 OPTIMIZATION (Session 237):
Replaces yfinance held_percent_insiders (~15% of yfinance_snapshot) with
authoritative SEC Form 4/5 insider transaction data (2-day lag).

Data source: SEC EDGAR Form 4/5 filings (insider transactions)
Update frequency: 2-day lag (near real-time regulatory filings)
Quality: Official insider transaction data > yfinance estimates

Run:
    python3 loaders/load_insider_holdings_sec.py [--symbols AAPL,MSFT]

NOTE (Session 237): Form 4/5 parser is scaffolded for future implementation.
Currently returns data_unavailable. Complex parsing deferred to Phase 2b.
Form 13F (institutional holdings) is the immediate priority (less parsing).
"""

import logging
import sys
from datetime import date, datetime
from typing import Any

from loaders.helpers.sec_base import SecLoaderBase
from loaders.runner import run_loader
from loaders.timeout_config import configure_socket_timeout
from utils.external.sec_edgar import SecEdgarClient
from utils.infrastructure.timezone import EASTERN_TZ

logger = logging.getLogger(__name__)
configure_socket_timeout(30)


class InsiderHoldingsSECLoader(SecLoaderBase):
    """Load insider ownership % from SEC Form 4/5 filings.

    PHASE 2: Eliminates yfinance held_percent_insiders (~15% yfinance load).
    Uses SEC Form 4/5 insider transactions (2-day lag, near real-time).

    Benefits:
    - Official SEC insider filings (regulatory authority)
    - Near real-time updates (2-day lag)
    - Granular transaction tracking (can see buy/sell patterns)
    - Eliminates yfinance rate-limiting dependency

    Trade-off: 2-day lag (acceptable for monitoring; real-time needs paid service).

    Implementation status (Session 237):
    - Loader scaffolded with placeholder data_unavailable responses
    - Form 4/5 XML parser requires XBRL parsing library (lxml, pandas-datareader)
    - Full implementation: estimated 1 week (Phase 2b)
    - For now: Form 13F (institutional holdings) is priority (simpler extraction)
    """

    table_name = "insider_holdings_sec"
    primary_key = ("symbol", "filing_date")
    watermark_field = "filing_date"
    exclude_etfs_from_symbols = True

    def __init__(self, backfill_days: int | None = None):
        super().__init__(backfill_days)
        self.sec_client = SecEdgarClient()

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch insider holdings from SEC Form 4/5 filings.

        SCAFFOLDED: Placeholder implementation. Full parser deferred to Phase 2b.

        Requires:
        - SEC EDGAR Form 4/5 XML parser (extract transaction data)
        - CIK to symbol mapping (from ticker cache)
        - Insider aggregation logic (sum holdings, track transactions)

        For now: Returns data_unavailable marker with clear reason.

        Args:
            symbol: Stock ticker symbol
            since: Minimum filing date to fetch (for incremental updates)

        Returns:
            List with insider holdings record or data_unavailable marker
        """
        now_et = datetime.now(EASTERN_TZ)

        # Placeholder: Form 4/5 parser not yet implemented
        # To enable: implement SEC EDGAR Form 4/5 XML parsing
        return self._unavailable_record(symbol, now_et, "form4_5_parser_pending_implementation")

    def _unavailable_record(self, symbol: str, now_et: datetime, reason: str) -> list[dict[str, Any]]:
        """Helper to create a data_unavailable record."""
        return [
            {
                "symbol": symbol,
                "filing_date": now_et.date(),
                "insider_ownership_pct": None,
                "number_of_insiders": None,
                "recent_buys": None,
                "recent_sells": None,
                "net_insider_transactions": None,
                "data_unavailable": True,
                "reason": reason,
                "latest_insider_filing_date": None,
                "sec_filing_url": None,
            }
        ]


def main() -> int:
    """Entry point for load_insider_holdings_sec.py."""
    try:
        return run_loader(InsiderHoldingsSECLoader)
    except Exception as e:
        logger.error(f"[INSIDER_SEC FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
