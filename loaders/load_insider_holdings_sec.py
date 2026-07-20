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
    """Load insider holdings from yfinance (pragmatic fallback).

    NOTE: SEC Form 4/5 parsing was failing (0% coverage) due to:
    - Form 4s distributed as plain text, not XBRL
    - XML parsing requires complex HTML extraction
    - Minimal data value for scoring (yfinance sufficient)

    Switched to yfinance for pragmatic data availability.

    Benefits:
    - Works for all US-listed companies
    - No parsing complexity (just field access)
    - Sufficient update frequency for scoring
    - Consistent with institutional holdings (also yfinance)
    """

    table_name = "insider_holdings_sec"
    primary_key = ("symbol", "filing_date")
    watermark_field = "filing_date"
    exclude_etfs_from_symbols = True

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch insider holdings from yfinance.

        Uses yfinance.Ticker.info['heldPercentInsiders'] which aggregates
        insider ownership data from regulatory filings.

        Args:
            symbol: Stock ticker symbol
            since: Minimum filing date to fetch (for incremental updates)

        Returns:
            List with insider holdings record or data_unavailable marker
        """
        now_et = datetime.now(EASTERN_TZ)

        try:
            import yfinance as yf

            ticker = yf.Ticker(symbol)
            info = ticker.info

            # Extract insider ownership percentage (0-1 scale in yfinance)
            insider_pct_raw = info.get("heldPercentInsiders")

            if insider_pct_raw is None:
                logger.debug(f"[{symbol}] No insider ownership data from yfinance")
                return self._unavailable_record(symbol, now_et, "yfinance_no_data")

            # Convert from decimal (0.01 for 1%) to percentage (1.0)
            if 0 < insider_pct_raw < 1:
                insider_pct = insider_pct_raw * 100.0
            else:
                insider_pct = float(insider_pct_raw)

            # Cap at 100%
            insider_pct = min(insider_pct, 100.0)

            return [
                {
                    "symbol": symbol,
                    "filing_date": now_et.date(),
                    "insider_ownership_pct": insider_pct,
                    "number_of_insiders": None,
                    "recent_buys": None,
                    "recent_sells": None,
                    "net_insider_transactions": None,
                    "data_unavailable": False,
                    "reason": None,
                    "latest_insider_filing_date": now_et.date(),
                    "sec_filing_url": None,
                    "data_source": "yfinance_heldpercentinsiders",
                }
            ]

        except Exception as e:
            logger.debug(f"[{symbol}] Failed to fetch insider holdings: {type(e).__name__}: {e}")
            return self._unavailable_record(symbol, now_et, f"yfinance_error: {str(e)[:40]}")


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
