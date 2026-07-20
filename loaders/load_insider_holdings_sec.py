#!/usr/bin/env python3
"""Insider Holdings Loader - yfinance (Pragmatic fallback).

PRIMARY: SEC Form 4/5 filings (insider transactions)
FALLBACK: yfinance.Ticker.info['heldPercentInsiders']

Data source: yfinance.Ticker.info['heldPercentInsiders']
Update frequency: Regular (sufficient for stock scoring)
Quality: yfinance aggregates insider ownership data

NOTE: SEC Form 4/5 parsing was failing (0% coverage) due to:
- Form 4s distributed as plain text, not XBRL
- XML parsing requires complex HTML extraction
- Minimal data value for scoring (yfinance sufficient)

Switched to yfinance for pragmatic data availability.

Run:
    python3 loaders/load_insider_holdings_sec.py [--symbols AAPL,MSFT]
"""

import logging
import sys
from datetime import date, datetime
from typing import Any

from loaders.runner import run_loader
from loaders.timeout_config import configure_socket_timeout
from utils.infrastructure.timezone import EASTERN_TZ
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)
configure_socket_timeout(30)


class InsiderHoldingsSECLoader(OptimalLoader):
    """Load insider holdings from SEC Form 4/5 filings (GOVERNANCE COMPLIANT).

    NOTE: Removed yfinance fallback per GOVERNANCE "no silent fallbacks" rule.

    SEC Form 4/5 parsing is complex (plain text filings, HTML extraction needed).
    Until proper SEC API integration is implemented, insider data will be marked unavailable.

    This is CORRECT per GOVERNANCE: better to have honest unavailability than
    rate-limited yfinance data mislabeled as "SEC" insider holdings.

    TODO: Implement SEC Form 4/5 parsing using SEC EDGAR API or
          integrate with official SEC insider filing database.
    """

    table_name = "insider_holdings_sec"
    primary_key = ("symbol", "filing_date")
    watermark_field = "filing_date"
    exclude_etfs_from_symbols = True

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch insider holdings from SEC Form 4/5 filings (GOVERNANCE COMPLIANT).

        GOVERNANCE: No yfinance fallback. Only official sources or explicit unavailability.

        SEC Form 4/5 parsing requires complex XBRL/HTML extraction from EDGAR.
        Until implemented, all data marked unavailable with clear reason.

        Args:
            symbol: Stock ticker symbol
            since: Minimum filing date to fetch (for incremental updates)

        Returns:
            List with data_unavailable marker (sec_form4_parsing_not_implemented)
        """
        now_et = datetime.now(EASTERN_TZ)

        logger.debug(
            f"[{symbol}] SEC Form 4/5 parsing not yet implemented. "
            f"Marking as unavailable per GOVERNANCE (no yfinance fallback)."
        )

        return self._unavailable_record(
            symbol,
            now_et,
            "sec_form4_parsing_not_implemented_use_official_sources_only"
        )


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
                "data_source": "none",
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
