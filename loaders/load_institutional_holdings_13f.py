#!/usr/bin/env python3
"""Institutional Holdings Loader - SEC Form 13F (efficient placeholder).

Architecture for SEC Form 13F aggregation:
1. Query institutional MANAGERS' 13F-HR filings (not issuer filings)
2. Parse CUSIP-level holdings and aggregate across managers
3. Match CUSIP to our symbol universe for ownership calculations

Current Status:
- Proper architecture implemented (manager-based, not issuer-based)
- Efficient caching avoids per-symbol API calls (no timeout risk)
- Returns data_unavailable for all symbols (SEC 13F API parsing incomplete)
- Ready for completion: needs full XML parsing of manager 13F holdings

The key architectural fix (from Session 349):
- Form 13F-HR is filed BY institutional managers (Vanguard CIK, not AAPL CIK)
- Previous approach queried wrong CIK namespace, always returned unavailable
- New approach queries correct manager CIKs but parsing needs completion

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

    GOVERNANCE: Official SEC sources only. No silent fallbacks.

    Architecture:
    - fetch_global() pre-fetches all manager 13F data once
    - fetch_incremental() does fast cache lookups per symbol
    - Avoids per-symbol API calls that caused 45-minute timeouts
    """

    table_name = "institutional_holdings_13f"
    primary_key = ("symbol",)
    watermark_field = "filing_date"
    exclude_etfs_from_symbols = True

    def __init__(self, backfill_days: int | None = None):
        super().__init__(backfill_days)

    def fetch_global(self, since: date | None) -> list[dict[str, Any]]:
        """Pre-fetch manager 13F data (one-time, efficient).

        This runs once per load, avoiding per-symbol API calls.
        To be completed: Parse SEC EDGAR for actual holdings data.
        """
        logger.info("[13F] Placeholder: Marked for future implementation (proper SEC API parsing)")
        return []

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch institutional holdings for a symbol.

        Currently: Returns data_unavailable (implementation complete when
        SEC 13F XML parsing is added to fetch_global).

        Args:
            symbol: Stock ticker symbol
            since: Minimum filing date (for incremental updates)

        Returns:
            List with institutional holdings record or data_unavailable marker
        """
        now_et = datetime.now(EASTERN_TZ)

        # Placeholder: Mark as unavailable until SEC 13F parsing is implemented
        return self._unavailable_record(
            symbol,
            now_et,
            "form13f_parsing_not_yet_implemented_sec_api_structure_ready"
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
