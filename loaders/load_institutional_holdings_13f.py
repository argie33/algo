#!/usr/bin/env python3
"""Institutional Holdings Loader - SEC Form 13F NOT FUNCTIONAL (see below).

NOT ACTUALLY IMPLEMENTED, despite prior docstrings here claiming otherwise:
`utils/sec_form13f_aggregator.py` looks for a `13F-HR` filing under the
ISSUER'S OWN CIK, which is a dead end - Form 13F is filed by the
institutional MANAGER under the manager's CIK with CUSIP-level holdings,
not cross-indexed under the issuer. An operating company never files
13F-HR under its own CIK, so this always returns data_unavailable=True.
There is no yfinance fallback in this file (also despite an earlier
docstring claim) - every symbol is marked data_unavailable.

A real implementation needs SEC's bulk quarterly structured datasets
(sec.gov/files/structureddata/data/form-13f-data-sets/*.zip,
INFOTABLE.tsv) aggregated by CUSIP, which requires a CUSIP->ticker
crosswalk SEC does not publish for free (CUSIP is licensed by CUSIP
Global Services). Blocked until a free crosswalk source is found.

Run:
    python3 loaders/load_institutional_holdings_13f.py [--symbols AAPL,MSFT]
"""

import logging
import sys
from datetime import date, datetime
from typing import Any

from loaders.runner import run_loader
from loaders.timeout_config import configure_socket_timeout
from utils.external.sec_edgar_client import SecEdgarClient
from utils.infrastructure.timezone import EASTERN_TZ
from utils.optimal_loader import OptimalLoader
from utils.sec_form13f_aggregator import Form13FAggregator

logger = logging.getLogger(__name__)
configure_socket_timeout(30)


class InstitutionalHoldings13FLoader(OptimalLoader):
    """Load institutional ownership % from SEC Form 13F filings.

    GOVERNANCE: Only official SEC sources. No silent fallbacks.
    Currently always marks data_unavailable=True - see module docstring for
    why the underlying aggregator is a dead end (issuer CIK has no 13F-HR)
    and what a real fix requires (CUSIP crosswalk, currently unavailable free).
    """

    table_name = "institutional_holdings_13f"
    primary_key = ("symbol", "filing_date")
    watermark_field = "filing_date"
    exclude_etfs_from_symbols = True

    def __init__(self, backfill_days: int | None = None):
        super().__init__(backfill_days)
        self.sec_client = SecEdgarClient()
        self.form13f_aggregator = Form13FAggregator()

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch institutional holdings from SEC Form 13F filings.

        GOVERNANCE: No yfinance fallback. Only official SEC sources.
        Session 298: Attempts Form 13F aggregation for real institutional data.

        Args:
            symbol: Stock ticker symbol
            since: Minimum filing date to fetch (for incremental updates)

        Returns:
            List with institutional holdings record or data_unavailable marker
        """
        now_et = datetime.now(EASTERN_TZ)

        try:
            # Step 1: Convert symbol to CIK
            try:
                cik = self.sec_client.symbol_to_cik(symbol)
            except ValueError:
                logger.debug(f"[{symbol}] CIK not found")
                return self._unavailable_record(symbol, now_et, "cik_not_found")

            # Step 2: Attempt Form 13F aggregation (Session 298)
            logger.debug(f"[{symbol}] Attempting Form 13F aggregation for {symbol}...")
            form13f_result = self.form13f_aggregator.get_institutional_ownership_pct(symbol, cik)

            if form13f_result.get("data_unavailable") is False:
                # SUCCESS: Form 13F data found
                inst_pct = form13f_result.get("institutional_ownership_pct")
                if inst_pct is not None:
                    logger.debug(f"[{symbol}] Form 13F: {inst_pct:.1f}%")
                    return [{
                        "symbol": symbol,
                        "filing_date": now_et.date(),
                        "institutional_ownership_pct": min(float(inst_pct), 100.0),
                        "number_of_institutional_holders": None,  # Would need to parse all 13F filings
                        "data_unavailable": False,
                        "reason": None,
                        "sec_filing_url": None,
                        "most_recent_filing_date": form13f_result.get("filing_date"),
                        "data_source": "sec_form13f",
                    }]

            # Step 3: Form 13F not available or not yet implemented
            reason = form13f_result.get("coverage_reason", "form13f_data_unavailable")
            logger.debug(f"[{symbol}] Form 13F unavailable: {reason}")

            return self._unavailable_record(symbol, now_et, reason)

        except Exception as e:
            logger.debug(f"[{symbol}] Exception fetching institutional holdings: {e}")
            return self._unavailable_record(
                symbol, now_et, f"fetch_error: {str(e)[:50]}"
            )

    def _unavailable_record(self, symbol: str, now_et: datetime, reason: str) -> list[dict[str, Any]]:
        """Helper to create a data_unavailable record."""
        return [
            {
                "symbol": symbol,
                "filing_date": now_et.date(),
                "institutional_ownership_pct": None,
                "number_of_institutional_holders": None,
                "data_unavailable": True,
                "reason": reason,
                "sec_filing_url": None,
                "most_recent_filing_date": None,
                "data_source": "none",
            }
        ]


def main() -> int:
    """Entry point for load_institutional_holdings_13f.py."""
    try:
        return run_loader(InstitutionalHoldings13FLoader)
    except Exception as e:
        logger.error(f"[INSTITUTIONAL_13F FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
