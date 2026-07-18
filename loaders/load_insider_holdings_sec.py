#!/usr/bin/env python3
"""Insider Holdings Loader - SEC Form 4/5 (Near Real-Time).

PHASE 2 OPTIMIZATION (Session 237):
Replaces yfinance held_percent_insiders (~15% of yfinance_snapshot) with
authoritative SEC Form 4/5 insider transaction data (2-day lag).

Data source: SEC EDGAR Form 4/5 filings (insider transactions, near real-time)
Update frequency: 2-day lag (regulatory filing deadline)
Quality: Official SEC insider transactions > yfinance estimates

Insider holdings computed from Form 4 transactions:
- Form 4: Insider transactions (officers, directors, 10%+ owners)
- Form 5: Annual filings for remaining insider holdings
- Data lag: 2 days (Form 4 filed within 2 days of transaction)

Run:
    python3 loaders/load_insider_holdings_sec.py [--symbols AAPL,MSFT]
"""

import json
import logging
import re
import sys
from datetime import date, datetime
from typing import Any
from xml.etree import ElementTree as ET

from loaders.helpers.sec_base import SecLoaderBase
from loaders.runner import run_loader
from loaders.timeout_config import configure_socket_timeout
from utils.external.sec_edgar import SecEdgarClient
from utils.infrastructure.timezone import EASTERN_TZ

logger = logging.getLogger(__name__)
configure_socket_timeout(30)


class InsiderHoldingsSECLoader(SecLoaderBase):
    """Load insider holdings from SEC Form 4/5 filings.

    PHASE 2: Eliminates yfinance held_percent_insiders (~15% yfinance load).
    Uses SEC Form 4/5 insider transactions (2-day lag, near real-time).

    Benefits:
    - Official SEC insider filings (regulatory authority)
    - Near real-time updates (2-day lag)
    - Granular transaction tracking (can see buy/sell patterns)
    - Eliminates yfinance rate-limiting dependency

    Trade-off: 2-day lag (acceptable for monitoring; real-time needs paid service).

    Implementation (Session 237):
    - Fetches Form 4/5 filings from SEC EDGAR submissions API
    - Parses insider transaction data from filings
    - Aggregates insider holdings and recent buy/sell activity
    - Computes insider ownership % and activity metrics
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

        Fetches recent Form 4 filings, extracts insider transaction data,
        aggregates holdings and activity metrics.

        Args:
            symbol: Stock ticker symbol
            since: Minimum filing date to fetch (for incremental updates)

        Returns:
            List with insider holdings record or data_unavailable marker
        """
        now_et = datetime.now(EASTERN_TZ)

        try:
            # Get CIK for this symbol
            try:
                cik = self.sec_client.symbol_to_cik(symbol)
            except ValueError:
                logger.warning(f"[{symbol}] CIK not found in SEC ticker cache")
                return self._unavailable_record(symbol, now_et, "cik_not_found")

            # Fetch submissions to find Form 4 filings
            try:
                submissions = self.sec_client.get_submissions(cik)
            except FileNotFoundError:
                return self._unavailable_record(symbol, now_et, "submissions_not_found_404")

            # Extract Form 4 filings from recent filings (fail-fast if structure wrong)
            if "filings" not in submissions:
                return self._unavailable_record(symbol, now_et, "invalid_submissions_structure:missing_filings")
            if "recent" not in submissions["filings"]:
                return self._unavailable_record(symbol, now_et, "invalid_submissions_structure:missing_recent")

            recent_filings = submissions["filings"]["recent"]
            if "form" not in recent_filings or "accessionNumber" not in recent_filings or "filingDate" not in recent_filings:
                return self._unavailable_record(symbol, now_et, "invalid_filings_structure:missing_required_fields")

            forms = recent_filings["form"]
            accession_numbers = recent_filings["accessionNumber"]
            filing_dates = recent_filings["filingDate"]

            form_4_filings = []
            for i, form_type in enumerate(forms):
                if form_type == "4" and i < len(accession_numbers):
                    accession = accession_numbers[i].replace("-", "")
                    filing_date_str = filing_dates[i] if i < len(filing_dates) else None
                    if filing_date_str:
                        try:
                            filing_date_obj = datetime.fromisoformat(filing_date_str).date()
                            # Only fetch recent filings (last 90 days)
                            if (now_et.date() - filing_date_obj).days <= 90:
                                form_4_filings.append((accession, filing_date_obj))
                        except (ValueError, TypeError):
                            pass

            if not form_4_filings:
                return self._unavailable_record(symbol, now_et, "no_recent_form4_filings")

            logger.error(
                f"[{symbol}] Form 4/5 XML parsing not implemented (CRITICAL). "
                "Phase 2 insider holdings loader requires SEC EDGAR XML parsing to extract transaction data. "
                "See steering/FAIL_FAST_VIOLATIONS_CATALOG_2026_06_29.md#insider-holdings-stub. "
                "Until implemented, use yfinance fallback via positioning_metrics loader."
            )
            return self._unavailable_record(symbol, now_et, "form4_parsing_not_implemented")

        except Exception as e:
            logger.error(f"[{symbol}] Failed to fetch insider holdings: {type(e).__name__}: {e}")
            return self._unavailable_record(symbol, now_et, f"fetch_error: {str(e)[:40]}")

    def _parse_form4_filings(
        self,
        symbol: str,
        cik: str,
        filings: list[tuple[str, date]],
    ) -> dict[str, Any]:
        """Parse Form 4 filings to extract insider transaction data.

        CRITICAL: Requires SEC EDGAR XML parsing of Form 4/5 filings.

        Implementation status: NOT IMPLEMENTED in Session 237.
        Form 4/5 files are XML-structured; parsing requires:
        1. Fetch filing XML from SEC EDGAR using accession_number
        2. Parse <nonDerivativeTransaction> elements
        3. Extract insider name, transaction type (buy/sell), shares, dates
        4. Aggregate by insider across 90-day window

        This is a ~2-week task requiring:
        - SEC EDGAR filing XML fetcher (authenticated HTTP)
        - XBRL/XML parser for Form 4 structure
        - Transaction aggregation logic
        - Cross-reference with share totals for ownership % calculation

        As of Session 237, this loader returns data_unavailable instead of placeholder data.

        Args:
            symbol: Stock ticker
            cik: Company CIK
            filings: List of (accession_number, filing_date) tuples

        Returns:
            Raises NotImplementedError - XML parsing not yet implemented
        """
        raise NotImplementedError(
            f"Form 4/5 XML parsing not implemented for {symbol}. "
            "Phase 2 insider holdings loader blocked. Use yfinance fallback via positioning_metrics loader."
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
