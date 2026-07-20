#!/usr/bin/env python3
"""Insider Holdings Loader - SEC Form 4/5 NOT YET IMPLEMENTED (No yfinance).

GOVERNANCE: No yfinance fallback exists in this file (despite an earlier
docstring here that claimed one) - all symbols are marked data_unavailable.

FEASIBILITY (investigated Session 298, this session): unlike Form 13F
(institutional holdings), Form 4/5 filings ARE cross-indexed under the
issuer's own CIK - confirmed via data.sec.gov/submissions/CIK{issuer}.json,
which lists hundreds of "4" entries for a large-cap issuer (e.g. 589 for
AAPL) alongside its 10-K/10-Q/8-K filings. So there's no CUSIP-crosswalk
problem here (unlike 13F).

What a real implementation needs:
- Per symbol: pull the issuer's submissions, filter form == "4"/"5", fetch
  each filing's ownership XML (not plain text - EDGAR's XML ownership
  documents replaced plain-text Form 4 filings years ago), and read
  <postTransactionAmounts><sharesOwnedFollowingTransaction> from the
  non-derivative table for the latest filing per unique reporting-owner CIK.
- Sum the latest per-insider holdings, divide by shares_outstanding
  (company_info_sec) for insider_ownership_pct.
- Rate-limit cost is the real blocker: large-caps can have 500+ Form 4
  filings; even fetching only the last ~2 years per symbol across ~4,700
  symbols is tens of thousands of requests at the project's SEC-loader
  parallelism cap (1-2 req/s). Realistic effort: 8-16h (parser + insider
  dedup logic + a multi-hour-runtime loader design), matching the Session
  298 estimate. Not attempted this session - lower priority now that
  positioning_metrics reaches ~93% from short_interest_finra alone
  (FINRA Query API fix, Session 298).

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
    # symbol-only: this is a current-snapshot table (one row per symbol), not a real
    # historical time series - filing_date gets set to "today" on every run since the
    # source is always data_unavailable, so a compound key here just accumulates a
    # fresh duplicate row forever instead of updating in place (fixed by migration 1124).
    primary_key = ("symbol",)
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
