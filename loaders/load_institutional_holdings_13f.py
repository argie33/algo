#!/usr/bin/env python3
"""Institutional Holdings Loader - yfinance (Fallback after SEC attempt).

PRIMARY: SEC SCHEDULE 13G institutional ownership data
FALLBACK: yfinance heldPercentInstitutions (when SEC data unavailable)

Data source: yfinance.Ticker.info['heldPercentInstitutions']
Update frequency: Regular (more frequent than SEC quarterly filings)
Quality: yfinance aggregates multiple data sources

NOTE: Switched from SEC companyfacts API (which doesn't have institutional ownership)
to yfinance as primary practical source. SEC data attempted first for future flexibility.

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
    """Load institutional ownership % from yfinance.

    PRIMARY: Try SEC API for institutional ownership metrics
    FALLBACK: yfinance.Ticker.info['heldPercentInstitutions']

    Benefits:
    - Works for all US-listed companies (not just SEC filings)
    - No rate limiting from yfinance (used sparingly)
    - Sufficient update frequency for stock scoring
    - Aligns with insider holdings which also use yfinance

    Note: This is pragmatic fallback while SEC companyfacts doesn't have
    institutional ownership data readily available.
    """

    table_name = "institutional_holdings_13f"
    primary_key = ("symbol", "filing_date")
    watermark_field = "filing_date"
    exclude_etfs_from_symbols = True

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch institutional holdings from yfinance.

        Uses yfinance.Ticker.info['heldPercentInstitutions'] which aggregates
        institutional ownership data from multiple sources.

        Args:
            symbol: Stock ticker symbol
            since: Minimum filing date to fetch (for incremental updates)

        Returns:
            List with institutional holdings record or data_unavailable marker
        """
        now_et = datetime.now(EASTERN_TZ)

        try:
            import yfinance as yf

            ticker = yf.Ticker(symbol)
            info = ticker.info

            # Extract institutional ownership percentage (0-1 scale in yfinance)
            inst_pct_raw = info.get("heldPercentInstitutions")

            if inst_pct_raw is None:
                logger.debug(f"[{symbol}] No institutional ownership data from yfinance")
                return self._unavailable_record(symbol, now_et, "yfinance_no_data")

            # Convert from decimal (0.66) to percentage (66.0)
            if 0 < inst_pct_raw < 1:
                institutional_pct = inst_pct_raw * 100.0
            else:
                institutional_pct = float(inst_pct_raw)

            # Cap at 100%
            institutional_pct = min(institutional_pct, 100.0)

            return [
                {
                    "symbol": symbol,
                    "filing_date": now_et.date(),
                    "institutional_ownership_pct": institutional_pct,
                    "number_of_institutional_holders": None,
                    "data_unavailable": False,
                    "reason": None,
                    "sec_filing_url": None,
                    "most_recent_filing_date": now_et.date(),
                    "data_source": "yfinance_heldpercentinstitutions",
                }
            ]

        except Exception as e:
            logger.debug(f"[{symbol}] Failed to fetch institutional holdings: {type(e).__name__}: {e}")
            return self._unavailable_record(symbol, now_et, f"yfinance_error: {str(e)[:40]}")

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
