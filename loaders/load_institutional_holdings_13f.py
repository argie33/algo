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
from utils.infrastructure.timezone import EASTERN_TZ
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class InstitutionalHoldings13FLoader(OptimalLoader):
    """Load institutional ownership % from SEC Form 13F filings.

    GOVERNANCE: Only official SEC sources. No silent fallbacks.
    Currently always marks data_unavailable=True - see module docstring for
    why the underlying aggregator is a dead end (issuer CIK has no 13F-HR)
    and what a real fix requires (CUSIP crosswalk, currently unavailable free).
    """

    table_name = "institutional_holdings_13f"
    # symbol-only: this is a current-snapshot table (one row per symbol), not a real
    # historical time series - filing_date gets set to "today" on every run since the
    # source is always data_unavailable, so a compound key here just accumulates a
    # fresh duplicate row forever instead of updating in place (fixed by migration 1124).
    primary_key = ("symbol",)
    watermark_field = "filing_date"
    exclude_etfs_from_symbols = True

    def __init__(self, backfill_days: int | None = None):
        super().__init__(backfill_days)

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch institutional holdings from SEC Form 13F filings.

        GOVERNANCE: No yfinance fallback. Only official SEC sources.
        NOT FUNCTIONAL: This loader always returns data_unavailable.

        Args:
            symbol: Stock ticker symbol
            since: Minimum filing date to fetch (for incremental updates)

        Returns:
            List with institutional holdings record or data_unavailable marker
        """
        now_et = datetime.now(EASTERN_TZ)

        # NOT IMPLEMENTED: Form 13F lookup requires CUSIP->ticker crosswalk (not available free).
        # See module docstring for details. Return unavailable immediately to avoid slow SEC API calls.
        return self._unavailable_record(
            symbol, now_et, "form13f_not_implemented_requires_cusip_crosswalk"
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
