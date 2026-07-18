#!/usr/bin/env python3
"""Insider Holdings Loader - SEC Form 4/5 (Near Real-Time).

PHASE 2 OPTIMIZATION (Session 234):
Replaces yfinance held_percent_insiders (~15% of yfinance_snapshot) with
authoritative SEC Form 4/5 insider transaction data (2-day lag).

Data source: SEC EDGAR Form 4/5 filings (insider transactions)
Update frequency: 2-day lag (near real-time regulatory filings)
Quality: Official insider transaction data > yfinance estimates

Run:
    python3 loaders/load_insider_holdings_sec.py [--symbols AAPL,MSFT]
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

logger = logging.getLogger(__name__)
configure_socket_timeout(30)

class InsiderHoldingsSECLoader(OptimalLoader):
    """Load insider ownership % from SEC Form 4/5 filings.
    
    PHASE 2: Eliminates yfinance held_percent_insiders (~15% yfinance load).
    Uses SEC Form 4/5 insider transactions (2-day lag, near real-time).
    
    Benefits:
    - Official SEC insider filings (regulatory authority)
    - Near real-time updates (2-day lag)
    - Granular transaction tracking (can see buy/sell patterns)
    - Eliminates yfinance rate-limiting dependency
    
    Trade-off: 2-day lag (acceptable for monitoring; real-time needs paid service).
    """

    table_name = "insider_holdings_sec"
    primary_key = ("symbol", "filing_date")
    watermark_field = "filing_date"
    exclude_etfs_from_symbols = True

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch insider holdings for a symbol from SEC Form 4/5 data.
        
        NOTE: Placeholder implementation. Actual fetching requires:
        - SEC EDGAR Form 4/5 parser (extract insider transactions)
        - CIK to symbol mapping (SEC central index key)
        - Insider aggregation logic (sum holdings by insider)
        
        For now: Returns data_unavailable marker (integration in progress).
        Returns:
            List with insider holdings dict or data_unavailable marker
        """
        now_et = datetime.now(EASTERN_TZ)
        
        # TODO: Implement SEC Form 4/5 fetching
        # Placeholder: mark as unavailable until integration complete
        return [
            {
                "symbol": symbol,
                "filing_date": now_et.date(),
                "insider_ownership_pct": None,
                "number_of_insiders": None,
                "recent_buys": None,
                "recent_sells": None,
                "data_unavailable": True,
                "reason": "form4_5_integration_pending",
                "updated_at": now_et,
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
