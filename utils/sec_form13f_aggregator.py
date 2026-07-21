#!/usr/bin/env python3
"""SEC Form 13F Aggregator - NOT FUNCTIONAL, always returns data_unavailable.

This looks up 13F-HR filings under the ISSUER's own CIK (`get_submissions(cik)`
where cik is the company being scored). That is a dead end: Form 13F is filed
by the institutional MANAGER under the manager's own CIK, listing CUSIP-level
holdings across many issuers - it is never filed by the operating company
itself. So `for form_type in recent_filings['form']: if form_type == '13F-HR'`
never matches for a real company, and every call falls through to
`_unavailable_result`. Even the "found a filing" branch below never parses
holdings (returns data_unavailable=True with a TODO) - there is no code path
in this file that produces a real percentage.

A real implementation requires SEC's bulk quarterly structured datasets
(sec.gov/files/structureddata/data/form-13f-data-sets/*.zip, INFOTABLE.tsv)
aggregated by CUSIP, which needs a CUSIP->ticker crosswalk SEC does not
publish for free. Blocked until a free crosswalk source is found.
"""

import logging
from typing import Any

from utils.external.sec_edgar_client import SecEdgarClient

logger = logging.getLogger(__name__)


class Form13FAggregator:
    """Aggregate Form 13F filings to calculate institutional ownership %.

    Form 13F-HR filings are quarterly reports filed by institutional investment
    managers with >$100M in securities holdings. By aggregating these filings,
    we can calculate what % of a company's shares are held by institutional investors.

    Limitations:
    - Only includes institutions managing >$100M (misses small institutions)
    - Quarterly data (not real-time)
    - 45-day filing delay (most recent data is ~2 months old)
    - Coverage limited to mid-cap and above (small-caps may not have enough 13F holders)
    """

    def __init__(self) -> None:
        self.sec_client = SecEdgarClient()

    def get_institutional_ownership_pct(self, symbol: str, cik: str) -> dict[str, Any]:
        """Calculate institutional ownership % by aggregating Form 13F filings.

        Args:
            symbol: Stock ticker symbol
            cik: Company CIK (from SEC)

        Returns:
            Dict with:
            - institutional_ownership_pct: Calculated % (0-100) or None if unavailable
            - coverage_reason: Why data is available or unavailable
            - filing_date: Most recent 13F filing date used
            - data_source: "sec_form13f" if successful
        """
        try:
            # Get company submissions to find 13F filings
            submissions = self.sec_client.get_submissions(cik)

            if not submissions or "filings" not in submissions:
                return self._unavailable_result(symbol, "submissions_not_found")

            recent_filings = submissions.get("filings", {}).get("recent", {})

            if not recent_filings or "form" not in recent_filings:
                return self._unavailable_result(symbol, "no_recent_filings")

            # Find most recent 13F-HR filing
            most_recent_13f_date = None
            most_recent_13f_accession = None

            for i, form_type in enumerate(recent_filings["form"]):
                if form_type == "13F-HR":
                    filing_date = (
                        recent_filings.get("filingDate", [])[i]
                        if i < len(recent_filings.get("filingDate", []))
                        else None
                    )
                    if filing_date:
                        most_recent_13f_date = filing_date
                        most_recent_13f_accession = (
                            recent_filings.get("accessionNumber", [])[i]
                            if i < len(recent_filings.get("accessionNumber", []))
                            else None
                        )
                        break  # First one is most recent

            if not most_recent_13f_date:
                return self._unavailable_result(symbol, "no_13f_filings")

            # Unreachable in practice (see module docstring) - kept for the day a
            # real INFOTABLE-based lookup replaces the issuer-CIK check above.
            logger.debug(
                f"[{symbol}] Found Form 13F filing: {most_recent_13f_date}, accession: {most_recent_13f_accession}"
            )

            return {
                "institutional_ownership_pct": None,  # Placeholder - needs full parser
                "coverage_reason": "form13f_parsing_not_yet_implemented_use_real_sec_data",
                "filing_date": most_recent_13f_date,
                "data_source": "sec_form13f",
                "accession_number": most_recent_13f_accession,
                "data_unavailable": True,  # Mark as unavailable until parser complete
                "note": "13F filing exists but requires XML parsing to extract holdings",
            }

        except Exception as e:
            logger.debug(f"[{symbol}] Form 13F aggregation failed: {e}")
            return self._unavailable_result(symbol, f"aggregation_error: {str(e)[:50]}")

    def _unavailable_result(self, symbol: str, reason: str) -> dict[str, Any]:
        """Return standardized unavailable result."""
        return {
            "institutional_ownership_pct": None,
            "coverage_reason": reason,
            "filing_date": None,
            "data_source": "none",
            "data_unavailable": True,
        }
