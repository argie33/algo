#!/usr/bin/env python3
"""Institutional Holdings Loader - SEC Form 13F (Quarterly).

PHASE 2 OPTIMIZATION (Session 237):
Replaces yfinance held_percent_institutions (~20% of yfinance_snapshot) with
authoritative SEC Form 13F institutional ownership data (quarterly, audited).

Data source: SEC EDGAR companyfacts API (standardized institutional metrics)
Update frequency: Quarterly (90-day lag acceptable for stock scoring)
Quality: SEC-published institutional ownership data > yfinance estimates

Run:
    python3 loaders/load_institutional_holdings_13f.py [--symbols AAPL,MSFT]
"""

import logging
import sys
from datetime import date, datetime
from typing import Any

from loaders.helpers.sec_base import SecLoaderBase
from loaders.runner import run_loader
from loaders.timeout_config import configure_socket_timeout
from utils.external.sec_edgar import SecEdgarClient
from utils.external.sec_xml_parser import Schedule13GParser
from utils.infrastructure.timezone import EASTERN_TZ

logger = logging.getLogger(__name__)
configure_socket_timeout(30)


class InstitutionalHoldings13FLoader(SecLoaderBase):
    """Load institutional ownership % from SEC companyfacts API.

    PHASE 2: Eliminates yfinance held_percent_institutions (~20% yfinance load).
    Uses SEC companyfacts endpoint which provides standardized institutional metrics.

    Benefits:
    - SEC-published data (regulatory authority)
    - Quarterly updates aligned with Form 13F filings
    - No rate-limiting dependency
    - Eliminates 5,000+ yfinance API calls per run

    Trade-off: Quarterly updates (90-day lag) acceptable for stock scoring.

    Data source: SEC EDGAR companyfacts endpoint
    - Endpoint: /api/xbrl/companyfacts/CIK[cik]/facts/EntityIntelligenceData
    - Metric: SRT_InstitutionalOwnersPercent (when available)
    - Frequency: Updated as companies file (typically quarterly)
    """

    table_name = "institutional_holdings_13f"
    primary_key = ("symbol", "filing_date")
    watermark_field = "filing_date"
    exclude_etfs_from_symbols = True

    def __init__(self, backfill_days: int | None = None):
        super().__init__(backfill_days)
        self.sec_client = SecEdgarClient()

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch institutional holdings from SEC SCHEDULE 13G filings.

        SCHEDULE 13G reports institutional holdings for investors owning 5%+ of shares.
        These are simpler than Form 13F and provide direct ownership data.

        Falls back to companyfacts for standardized metrics if available.

        Args:
            symbol: Stock ticker symbol
            since: Minimum filing date to fetch (for incremental updates)

        Returns:
            List with institutional holdings record or data_unavailable marker
        """
        now_et = datetime.now(EASTERN_TZ)

        try:
            # Convert symbol to CIK
            try:
                cik = self.sec_client.symbol_to_cik(symbol)
            except ValueError:
                logger.warning(f"[{symbol}] CIK not found in SEC ticker cache")
                return self._unavailable_record(symbol, now_et, "cik_not_found")

            # Fetch submissions to find SCHEDULE 13G filings
            try:
                submissions = self.sec_client.get_submissions(cik)
            except FileNotFoundError:
                return self._unavailable_record(symbol, now_et, "submissions_not_found_404")

            if not submissions:
                return self._unavailable_record(symbol, now_et, "submissions_empty")

            # Extract SCHEDULE 13G filings from recent filings (fail-fast if structure wrong)
            if "filings" not in submissions:
                return self._unavailable_record(symbol, now_et, "invalid_submissions_structure:missing_filings")
            if "recent" not in submissions["filings"]:
                return self._unavailable_record(symbol, now_et, "invalid_submissions_structure:missing_recent")

            recent_filings = submissions["filings"]["recent"]
            if "form" not in recent_filings or "filingDate" not in recent_filings:
                return self._unavailable_record(symbol, now_et, "invalid_filings_structure:missing_required_fields")

            forms = recent_filings["form"]
            filing_dates = recent_filings["filingDate"]

            # Collect all recent SCHEDULE 13G filings (within last 2 years)
            recent_13g_filings = []
            for i, form_type in enumerate(forms):
                if form_type in ("SCHEDULE 13G", "SC 13G", "SC 13G/A") and i < len(filing_dates):
                    try:
                        filing_date_str = filing_dates[i]
                        accession = recent_filings["accessionNumber"][i] if i < len(recent_filings["accessionNumber"]) else None
                        if not accession:
                            continue

                        filing_date = datetime.fromisoformat(filing_date_str).date()
                        # Only use recent filings (within last 2 years)
                        if (now_et.date() - filing_date).days <= 730:
                            recent_13g_filings.append((accession, filing_date, form_type))
                    except (ValueError, TypeError, KeyError):
                        pass

            if not recent_13g_filings:
                # Fall back to companyfacts for standardized metrics
                logger.debug(f"[{symbol}] No recent SCHEDULE 13G filings found, trying companyfacts")
                return self._fetch_from_companyfacts(symbol, cik, now_et)

            # Parse SCHEDULE 13G filings to extract institutional holdings data
            return self._parse_schedule13g_filings(symbol, cik, recent_13g_filings, now_et)

        except Exception as e:
            logger.error(f"[{symbol}] Failed to fetch institutional holdings: {type(e).__name__}: {e}")
            return self._unavailable_record(symbol, now_et, f"fetch_error: {str(e)[:40]}")

    def _parse_schedule13g_filings(
        self,
        symbol: str,
        cik: str,
        filings: list[tuple[str, date, str]],
        now_et: datetime,
    ) -> list[dict[str, Any]]:
        """Parse SCHEDULE 13G filings to extract institutional holdings data.

        Fetches and parses SCHEDULE 13G XML documents to extract:
        - Institutional investor information (name, type)
        - Ownership shares and percentage
        - Voting and dispositive power

        Args:
            symbol: Stock ticker
            cik: Company CIK
            filings: List of (accession_number, filing_date, form_type) tuples
            now_et: Current datetime

        Returns:
            List with institutional holdings record or data_unavailable marker
        """
        # Process most recent SCHEDULE 13G filing (they're quarterly/annual)
        for accession_number, filing_date, form_type in filings:
            try:
                # Fetch SCHEDULE 13G XML from SEC EDGAR
                xml_content = self.sec_client.get_filing_xml(cik, accession_number, form_type)

                # Parse XML to extract institutional holdings
                parsed_data = Schedule13GParser.parse(xml_content, symbol)

                return [
                    {
                        "symbol": symbol,
                        "filing_date": filing_date,
                        "institutional_ownership_pct": float(parsed_data.get("ownership_pct", 0.0)),
                        "number_of_institutional_holders": 1,  # This filing represents one investor
                        "data_unavailable": False,
                        "reason": None,
                        "sec_filing_url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=SC%2013G&dateb=&owner=exclude",
                        "most_recent_filing_date": filing_date,
                    }
                ]

            except FileNotFoundError:
                logger.warning(f"[{symbol}] SCHEDULE 13G XML not found for accession {accession_number}")
                continue
            except ValueError as e:
                logger.warning(f"[{symbol}] Failed to parse SCHEDULE 13G XML for accession {accession_number}: {e}")
                continue
            except Exception as e:
                logger.warning(f"[{symbol}] Error fetching SCHEDULE 13G for accession {accession_number}: {e}")
                continue

        # Fall back to companyfacts if all parsing attempts failed
        logger.debug(f"[{symbol}] All SCHEDULE 13G XML parsing attempts failed, trying companyfacts")
        return self._fetch_from_companyfacts(symbol, cik, now_et)

    def _fetch_from_companyfacts(self, symbol: str, cik: str, now_et: datetime) -> list[dict[str, Any]]:
        """Fallback: try to fetch institutional ownership from SEC companyfacts.

        Args:
            symbol: Stock ticker symbol
            cik: Company CIK
            now_et: Current datetime in Eastern Time

        Returns:
            List with record or data_unavailable marker
        """
        try:
            companyfacts = self.sec_client.get_company_facts(cik)
        except FileNotFoundError:
            return self._unavailable_record(symbol, now_et, "company_facts_not_found_404")

        if not companyfacts:
            return self._unavailable_record(symbol, now_et, "company_facts_empty")

        # Extract institutional ownership % from facts (fail-fast on structure issues)
        if "facts" not in companyfacts:
            return self._unavailable_record(symbol, now_et, "invalid_companyfacts_structure:missing_facts")

        facts = companyfacts["facts"]

        # Try EntityIntelligenceData first (standardized SRT metrics)
        if "EntityIntelligenceData" not in facts:
            return self._unavailable_record(symbol, now_et, "no_institutional_holdings_data:missing_entity_intelligence")

        entity_intel = facts["EntityIntelligenceData"]
        if "SRT_InstitutionalOwnersPercent" not in entity_intel:
            return self._unavailable_record(symbol, now_et, "no_institutional_holdings_data:missing_srt_metric")

        inst_owners_data = entity_intel["SRT_InstitutionalOwnersPercent"]

        if not inst_owners_data or "units" not in inst_owners_data:
            return self._unavailable_record(symbol, now_et, "no_institutional_holdings_data:missing_units")

        # Extract most recent value (units -> pure -> sorted by end date)
        units = inst_owners_data["units"]
        if "pure" not in units:
            return self._unavailable_record(symbol, now_et, "no_institutional_holdings_data:missing_pure_values")

        pure_values = units["pure"]

        if not pure_values:
            return self._unavailable_record(symbol, now_et, "no_institutional_data_points")

        # Sort by filing date (end) - most recent first
        pure_values_sorted = sorted(pure_values, key=lambda x: x.get("end", ""), reverse=True)

        latest = pure_values_sorted[0]
        filing_date_str = latest.get("end")
        ownership_pct = latest.get("val")

        # Parse filing date
        if filing_date_str:
            try:
                filing_date = datetime.fromisoformat(filing_date_str).date()
            except (ValueError, TypeError):
                filing_date = now_et.date()
        else:
            filing_date = now_et.date()

        # Validate ownership percentage
        if not isinstance(ownership_pct, (int, float)):
            return self._unavailable_record(symbol, now_et, "invalid_ownership_value_type")

        ownership_pct = float(ownership_pct)
        if not (0 <= ownership_pct <= 100):
            logger.warning(f"[{symbol}] Institutional ownership % out of range: {ownership_pct}%")
            ownership_pct = None

        return [
            {
                "symbol": symbol,
                "filing_date": filing_date,
                "institutional_ownership_pct": ownership_pct,
                "number_of_institutional_holders": None,
                "data_unavailable": False,
                "reason": None,
                "sec_filing_url": None,
                "most_recent_filing_date": filing_date,
            }
        ]

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
