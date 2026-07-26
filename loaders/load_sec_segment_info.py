#!/usr/bin/env python3
"""SEC XBRL Segment Info Loader - Extracts business segment data from 10-K/10-Q filings.

Parses SEC EDGAR companyfacts (XBRL) to extract segment disclosures (ASC 280):
  - Number of reportable operating segments
  - Segment names and revenue
  - Revenue concentration (Herfindahl index)
  - Segment diversification metrics

Writes to sec_segment_info table, consumed by load_sec_segment_metrics.py.

Run: python3 loaders/load_sec_segment_info.py [--symbols AAPL,MSFT] [--parallelism 2]
"""

import logging
import sys
from datetime import date, datetime
from typing import Any

from loaders.helpers.sec_base import SecLoaderBase
from loaders.runner import run_loader
from utils.external.sec_edgar_client import SecEdgarClient
from utils.external.sec_xbrl_segments import XBRLSegmentParser

logger = logging.getLogger(__name__)


class SecSegmentInfoLoader(SecLoaderBase):
    """Extract segment disclosure data from SEC 10-K/10-Q XBRL filings.

    Uses companyfacts API to fetch XBRL facts per symbol, then parses segment data
    (ASC 280) and writes to sec_segment_info table as the source for
    load_sec_segment_metrics.py (which computes diversification scoring).

    ARCHITECTURAL NOTE: SEC companyfacts API limitation
    ─────────────────────────────────────────────────
    companyfacts is a simplified JSON export that loses XBRL context dimension
    information needed to map revenues to specific segments. This means:

    ✓ Can extract: segment count (NumberOfReportableSegments)
    ✗ Cannot extract: per-segment revenue for concentration metrics

    Why: XBRL XML uses contextRef attributes to associate facts with dimensional
    values. The companyfacts JSON flattens this away.

    Implication: Returns data_unavailable when segment revenue missing.

    If segment diversification becomes critical for trading strategy:
    - Fetch raw 10-K/10-Q XML files directly
    - Parse with full XBRL context dimension support
    - See session_453_xbrl_decision.md for detailed analysis
    """

    table_name = "sec_segment_info"
    primary_key = ("symbol", "fiscal_year", "fiscal_period", "segment_name")
    watermark_field = "parsed_at"
    exclude_etfs_from_symbols = True
    max_fail_rate = 70.0  # Many companies are single-segment; allow partial data writes

    def __init__(self) -> None:
        """Initialize loader with SEC Edgar client."""
        super().__init__()
        self.sec_client = SecEdgarClient()

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Extract segment info for one symbol from SEC XBRL - try aggressively.

        Strategy:
        1. First try companyfacts API (fast)
        2. If no segment data, fetch raw XBRL XML from latest 10-K and parse directly
        3. Only mark unavailable if both approaches fail

        Returns:
            List of segment records for all filings found (1+ per symbol if multiple
            fiscal years/periods available), or data_unavailable marker if no segment
            data found.
        """
        try:
            # Get CIK for symbol
            try:
                cik = self.sec_client.symbol_to_cik(symbol)
            except ValueError:
                return [self._unavailable_marker(symbol, "symbol_not_found")]

            # Fetch companyfacts XBRL data (JSON)
            # This returns JSON with all us-gaap facts for the company
            try:
                facts_response = self.sec_client.get_company_facts(cik)
            except FileNotFoundError:
                facts_response = None
            except RuntimeError as e:
                logger.warning(f"[{symbol}] SEC API error fetching companyfacts: {e}")
                facts_response = None

            segment_data = None
            if facts_response and facts_response.get('facts'):
                # Try companyfacts API first
                segment_data = XBRLSegmentParser.parse_companyfacts(facts_response, symbol)
                if segment_data.get('data_available'):
                    logger.info(f"[{symbol}] Segment data found via companyfacts API")

            # If companyfacts didn't have segment data, try raw XBRL XML (more aggressive)
            if not segment_data or not segment_data.get('data_available'):
                logger.info(f"[{symbol}] No segment data in companyfacts, trying raw XBRL XML")
                try:
                    # Get latest 10-K filing
                    submissions = self.sec_client.get_submissions(cik)
                    latest_10k = self._find_latest_10k(submissions)

                    if latest_10k:
                        # get_filing_xml/_get_primary_document match against SEC's
                        # dashed accessionNumber list - the stripped 'accession' key
                        # never matches, silently falling through to the except below
                        # on every call. Confirmed live: get_filing_xml requires the
                        # dashed form.
                        accession = latest_10k['accession_formatted']
                        try:
                            xml_content = self.sec_client.get_filing_xml(cik, accession, '10-K')
                            logger.debug(f"[{symbol}] Fetched raw XBRL XML for {accession}")
                            segment_data = XBRLSegmentParser.extract_segment_revenue_from_xbrl_xml(
                                xml_content, symbol
                            )
                            if segment_data.get('data_available'):
                                logger.info(f"[{symbol}] Segment data found in raw XBRL XML")
                        except (FileNotFoundError, RuntimeError) as e:
                            logger.debug(f"[{symbol}] Failed to fetch/parse raw XBRL: {e}")
                except Exception as e:
                    logger.debug(f"[{symbol}] Error trying raw XBRL approach: {e}")

            # Use whatever segment data we found, or mark unavailable
            if not segment_data or not segment_data.get('data_available'):
                return [self._unavailable_marker(
                    symbol,
                    segment_data.get('reason', 'no_segment_data') if segment_data else 'no_segment_data'
                )]

            # Extract individual segments
            segments = segment_data.get('segments', [])
            if not segments:
                return [self._unavailable_marker(symbol, "no_segments_found")]

            records = []

            # Get fiscal year/period from the facts response metadata
            # SEC EDGAR companyfacts includes filing metadata
            filing_date = self._extract_filing_date(facts_response)
            fiscal_year = filing_date.year if filing_date else date.today().year
            fiscal_period = "FY"  # Simplified: assume annual for now

            # Write aggregate segment metrics
            records.append({
                "symbol": symbol,
                "fiscal_year": fiscal_year,
                "fiscal_period": fiscal_period,
                "filing_date": filing_date or date.today(),
                "segment_count": segment_data['segment_count'],
                "segment_type": "operating",
                "segment_name": "AGGREGATE",
                "segment_revenue": None,
                "segment_operating_income": None,
                "segment_assets": None,
                "largest_segment_revenue_pct": segment_data['largest_segment_revenue_pct'],
                "revenue_concentration_hhi": segment_data['revenue_concentration_hhi'],
                "segment_data_available": segment_data['data_available'],
                "data_unavailable": False,
                "reason": None,
                "fetched_at": date.today(),
                "parsed_at": date.today(),
            })

            # Write individual segment data
            for i, seg in enumerate(segments, 1):
                records.append({
                    "symbol": symbol,
                    "fiscal_year": fiscal_year,
                    "fiscal_period": fiscal_period,
                    "filing_date": filing_date or date.today(),
                    "segment_count": segment_data['segment_count'],
                    "segment_type": "operating",
                    "segment_name": seg.get('name', f"Segment_{i}"),
                    "segment_revenue": seg.get('revenue'),
                    "segment_operating_income": seg.get('operating_income'),
                    "segment_assets": seg.get('assets'),
                    "largest_segment_revenue_pct": segment_data['largest_segment_revenue_pct'],
                    "revenue_concentration_hhi": segment_data['revenue_concentration_hhi'],
                    "segment_data_available": segment_data['data_available'],
                    "data_unavailable": False,
                    "reason": None,
                    "fetched_at": date.today(),
                    "parsed_at": date.today(),
                })

            return records

        except Exception as e:
            logger.error(f"[{symbol}] Segment extraction failed: {type(e).__name__}: {str(e)[:300]}", exc_info=True)
            return [self._unavailable_marker(symbol, f"extraction_error:{type(e).__name__}")]

    def _find_latest_10k(self, submissions: dict) -> dict | None:
        """Find the most recent 10-K filing in the submissions list.

        SEC filings format is columnar: {'accessionNumber': [...], 'form': [...], ...}
        where each list value at index i is one filing's data.

        Returns:
            Dict with 'accession_formatted' (dashed, e.g. "0001193125-24-001234" -
            the format SecEdgarClient's fetch methods match against), or None if no
            10-K found.
        """
        filings = submissions.get('filings', {}).get('recent', {})
        if not isinstance(filings, dict):
            return None

        forms = filings.get('form', [])
        accessions = filings.get('accessionNumber', [])

        for i, form in enumerate(forms):
            if form == '10-K' and i < len(accessions):
                return {'accession_formatted': accessions[i]}
        return None

    def _extract_filing_date(self, facts_response: dict) -> date | None:
        """Extract most recent filing date from companyfacts response.

        Companyfacts includes metadata with filing dates. We look for the most recent
        filing date in the XBRL facts that have context periods.
        """
        try:
            # Try to extract filing dates from the facts structure
            us_gaap = facts_response.get('facts', {}).get('us-gaap', {})

            latest_date = None
            for _concept_name, concept_data in us_gaap.items():
                if isinstance(concept_data, dict) and 'units' in concept_data:
                    units = concept_data['units']
                    for _unit, facts_list in units.items():
                        if isinstance(facts_list, list):
                            for fact in facts_list:
                                if isinstance(fact, dict):
                                    # Facts have 'filed' and 'end' dates
                                    filed_str = fact.get('filed')
                                    if filed_str:
                                        try:
                                            filed = datetime.strptime(filed_str, '%Y-%m-%d').date()
                                            if latest_date is None or filed > latest_date:
                                                latest_date = filed
                                        except (ValueError, TypeError):
                                            pass

            if latest_date:
                return latest_date
            return None
        except Exception:
            return None

    def _unavailable_marker(self, symbol: str, reason: str) -> dict[str, Any | None]:
        """Build a data_unavailable row for a symbol with no segment disclosure."""
        return {
            "symbol": symbol,
            "fiscal_year": date.today().year,
            "fiscal_period": "FY",
            "filing_date": date.today(),
            "segment_count": None,
            "segment_type": None,
            "segment_name": "AGGREGATE",
            "segment_revenue": None,
            "segment_operating_income": None,
            "segment_assets": None,
            "largest_segment_revenue_pct": None,
            "revenue_concentration_hhi": None,
            "segment_data_available": False,
            "data_unavailable": True,
            "reason": reason,
            "fetched_at": date.today(),
            "parsed_at": date.today(),
        }


def main() -> int:
    """Wrapped main with exception handling."""
    try:
        return run_loader(SecSegmentInfoLoader)
    except Exception as e:
        logger.error(f"[SEC_SEGMENT_INFO FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
