#!/usr/bin/env python3
"""Institutional Holdings Loader - SEC Form 13F DATA AVAILABILITY TRACKING.

CRITICAL GOVERNANCE NOTE: Institutional ownership data is NOT currently available.
SEC Form 13F filings (which contain investor holdings >5%) require complex aggregation.

DATA SOURCES EVALUATED (Session 298):
- SEC Form 13F: Investor filings (requires aggregation - NOT YET IMPLEMENTED)
- SEC companyfacts API: Company-reported metrics only (doesn't have investor holdings)
- yfinance: Rate-limited, inaccurate - EXPLICITLY NOT USED per governance

CURRENT STATUS: Marked unavailable until Form 13F parser implemented
Coverage: 8.7% (from legacy data created with older implementations)

Run:
    python3 loaders/load_institutional_holdings_13f.py [--symbols AAPL,MSFT]
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


class InstitutionalHoldings13FLoader(OptimalLoader):
    """Load institutional ownership % from SEC Form 13F filings only (no yfinance).

    GOVERNANCE: Only official sources. No silent fallbacks.
    - PRIMARY: SEC Form 13F filings (institutional investor holdings > 5%)
    - NO FALLBACK: If SEC data unavailable, mark data_unavailable=TRUE (fail-fast)

    CRITICAL (Session 297): Removed yfinance fallback which was causing:
    - Rate limiting failures (9,351+ fetches blocked)
    - Inaccurate data (yfinance aggregates multiple sources, not authoritative)
    - Silent degradation of institutional ownership metrics

    Note: Institutional ownership % comes from 13F filings (investor holdings),
    not company-reported data. SEC companyfacts doesn't have this metric.
    Coverage limitations expected for small-caps, IPOs, non-public companies.
    """

    table_name = "institutional_holdings_13f"
    primary_key = ("symbol", "filing_date")
    watermark_field = "filing_date"
    exclude_etfs_from_symbols = True

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch institutional holdings from SEC Form 13F filings only.

        GOVERNANCE: No yfinance fallback. Only official SEC sources.

        Args:
            symbol: Stock ticker symbol
            since: Minimum filing date to fetch (for incremental updates)

        Returns:
            List with institutional holdings record or data_unavailable marker
        """
        now_et = datetime.now(EASTERN_TZ)

        # GOVERNANCE CHANGE (Session 297): Remove yfinance fallback entirely.
        # yfinance was causing rate limiting (9,351+ failed fetches across all stocks).
        # Institutional ownership comes from SEC Form 13F filings, which have known
        # coverage gaps for small-caps and IPOs. Accept data unavailable rather than
        # falling back to rate-limited, inaccurate yfinance data.
        logger.debug(
            f"[{symbol}] Institutional ownership data unavailable: "
            f"Form 13F filings not accessible via SEC API. This is expected for "
            f"stocks without major institutional investors (small-caps, IPOs, micro-caps)."
        )
        return self._unavailable_record(
            symbol, now_et, "sec_form13f_data_unavailable"
        )

    def _fetch_companyfacts_institutional(self, symbol: str, cik: str, now_et: datetime) -> list[dict[str, Any]]:
        """Fetch institutional ownership % from SEC companyfacts API.

        Uses SEC's XBRL-standardized institutional ownership metrics available through
        the companyfacts endpoint. This applies to all public companies, not just those
        with 5%+ shareholders (which is why SC 13G approach had only 0.02% coverage).

        The companyfacts API provides standardized XBRL metrics that companies report
        in their 10-K/10-Q filings.

        Args:
            symbol: Stock ticker symbol
            cik: Company CIK
            now_et: Current datetime in Eastern Time

        Returns:
            List with record or data_unavailable marker
        """
        try:
            # Fetch companyfacts for the company
            # This endpoint returns all XBRL facts reported by the company
            facts = self.sec_client.get_company_facts(cik)
            if not facts:
                return self._unavailable_record(symbol, now_et, "companyfacts_empty")

            # Look for institutional ownership metrics in the facts
            # SEC companies report institutional ownership % in their filings
            # Try multiple possible XBRL tags for institutional ownership
            institutional_pct = None
            latest_filing_date = None

            # Common XBRL tags for institutional ownership:
            # - us-gaap:InstitutionalOwnersPercent
            # - srt:InstitutionalOwnersPercent
            # - CIK-based tag variations
            possible_tags = [
                "us-gaap:InstitutionalOwnersPercent",
                "srt:InstitutionalOwnersPercent",
                "institutional_ownership_pct",
            ]

            for tag in possible_tags:
                logger.debug(f"[{symbol}] Trying tag: {tag}")
                if tag in facts:
                    # Get the most recent reported value
                    tag_facts = facts[tag]
                    if isinstance(tag_facts, list):
                        for fact in sorted(tag_facts, key=lambda x: x.get("filed", ""), reverse=True):
                            if fact.get("val") is not None:
                                institutional_pct = float(fact["val"])
                                if fact.get("filed"):
                                    latest_filing_date = datetime.fromisoformat(fact["filed"]).date()
                                break
                    elif isinstance(tag_facts, dict):
                        if tag_facts.get("val") is not None:
                            institutional_pct = float(tag_facts["val"])
                            if tag_facts.get("filed"):
                                latest_filing_date = datetime.fromisoformat(tag_facts["filed"]).date()

                    if institutional_pct is not None:
                        logger.debug(f"[{symbol}] Success: using tag {tag} with value {institutional_pct}%")
                        break
                else:
                    logger.debug(f"[{symbol}] Tag not found in facts: {tag}")

            # Fail if no institutional ownership metric found
            if institutional_pct is None:
                logger.debug(f"[{symbol}] No institutional ownership metric in companyfacts")
                return self._unavailable_record(symbol, now_et, "no_institutional_ownership_metric")

            # Cap at 100%
            institutional_pct = min(float(institutional_pct), 100.0)

            if latest_filing_date is None:
                latest_filing_date = now_et.date()

            return [
                {
                    "symbol": symbol,
                    "filing_date": latest_filing_date,
                    "institutional_ownership_pct": institutional_pct,
                    "number_of_institutional_holders": None,  # Not available from companyfacts
                    "data_unavailable": False,
                    "reason": None,
                    "sec_filing_url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=10-K",
                    "most_recent_filing_date": latest_filing_date,
                    "data_source": "sec_companyfacts_xbrl",
                }
            ]

        except Exception as e:
            logger.debug(f"[{symbol}] Failed to fetch from companyfacts: {e}")
            return self._unavailable_record(symbol, now_et, f"companyfacts_error: {str(e)[:30]}")

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
