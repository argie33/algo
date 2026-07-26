#!/usr/bin/env python3
"""Form 8-K Current Reports Loader - SEC EDGAR.

Loads SEC Form 8-K filings (Current Reports) to identify material events
that may impact trading signals. 8-K filings must be made within 4 business
days of a material event.

Data source: SEC EDGAR Submissions API
Update frequency: Daily (events are reported as filed)

Material events tracked:
- Item 1.01: Bankruptcy or material loss
- Item 2.01: Completion of acquisition/disposition
- Item 2.04: Material definitive agreement changes
- Item 3.01: Default under material agreement
- Item 5.02: Changes in directors/officers
- Item 8.01: Other events (catch-all for material events)

Run:
    python3 loaders/load_current_reports_8k.py [--symbols AAPL,MSFT]
"""

import logging
import sys
from datetime import date, datetime, timedelta
from typing import Any

from loaders.helpers.sec_base import SecLoaderBase
from loaders.runner import run_loader
from loaders.timeout_config import configure_socket_timeout
from utils.external.sec_edgar import SecEdgarClient
from utils.infrastructure.timezone import EASTERN_TZ
from utils.loaders.exception_handler import handle_exception

logger = logging.getLogger(__name__)
configure_socket_timeout(30)


class CurrentReports8KLoader(SecLoaderBase):
    """Load SEC Form 8-K Current Reports.

    Form 8-K must be filed within 4 business days of a material event.
    This loader tracks all 8-K filings to identify corporate events that
    may impact stock prices and trading signals.

    Key features:
    - Official SEC EDGAR source (authoritative)
    - Material event classification (Items 1.01-8.01)
    - Event summary and description extraction
    - Daily update cadence
    """

    table_name = "current_reports_8k"
    primary_key = ("symbol", "accession_number")
    watermark_field = "filing_date"
    exclude_etfs_from_symbols = True
    max_fail_rate = 2.0  # SEC API occasionally fails on isolated symbols

    def __init__(self, backfill_days: int | None = None):
        super().__init__(backfill_days)
        self.sec_client = SecEdgarClient()

    def _extract_8k_items(self, filing_text: str) -> dict[str, bool]:
        """Extract which 8-K items are disclosed in filing.

        Scans filing text for Item tags that indicate material events.
        Returns dict with item flags set to True if item is disclosed.
        """
        items = {
            "item_1_01": False,  # Bankruptcy/material loss
            "item_1_02": False,  # Unregistered sales
            "item_1_03": False,  # Bankruptcy proceedings
            "item_2_01": False,  # Acquisition/disposition
            "item_2_02": False,  # Results of operations
            "item_2_03": False,  # Material obligations
            "item_2_04": False,  # Definitive agreement changes
            "item_2_05": False,  # Exit/disposal costs
            "item_2_06": False,  # Material impairments
            "item_2_07": False,  # Regulation FD
            "item_2_08": False,  # Other events
            "item_3_01": False,  # Default under agreement
            "item_3_02": False,  # Unregistered sales
            "item_3_03": False,  # Material modification
            "item_4_01": False,  # Accountant changes
            "item_4_02": False,  # Non-reliance
            "item_5_01": False,  # Costs
            "item_5_02": False,  # Bankruptcy
            "item_5_03": False,  # Amendment to articles
            "item_5_05": False,  # Amendments
            "item_5_07": False,  # Matters to vote
            "item_6_01": False,  # Bankruptcy
            "item_7_01": False,  # Regulation FD
            "item_8_01": False,  # Other events
            "item_9_01": False,  # Exhibits
        }

        # Simple heuristic: search for Item tags in filing text
        text_upper = filing_text.upper()

        item_patterns = {
            "item_1_01": "ITEM 1.01",
            "item_2_01": "ITEM 2.01",
            "item_2_02": "ITEM 2.02",
            "item_2_03": "ITEM 2.03",
            "item_2_04": "ITEM 2.04",
            "item_2_05": "ITEM 2.05",
            "item_2_06": "ITEM 2.06",
            "item_2_07": "ITEM 2.07",
            "item_2_08": "ITEM 2.08",
            "item_3_01": "ITEM 3.01",
            "item_3_02": "ITEM 3.02",
            "item_3_03": "ITEM 3.03",
            "item_4_01": "ITEM 4.01",
            "item_4_02": "ITEM 4.02",
            "item_5_02": "ITEM 5.02",
            "item_5_03": "ITEM 5.03",
            "item_5_07": "ITEM 5.07",
            "item_8_01": "ITEM 8.01",
            "item_9_01": "ITEM 9.01",
        }

        for key, pattern in item_patterns.items():
            if pattern in text_upper:
                items[key] = True

        return items

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch Form 8-K filings for symbol since given date.

        Args:
            symbol: Stock symbol
            since: Only fetch filings on or after this date

        Returns:
            List of 8-K filing records or data_unavailable marker
        """
        try:
            now_et = datetime.now(EASTERN_TZ).date()
            # Get CIK for symbol
            cik = self._get_cik(symbol)
            if not cik:
                return self._unavailable_record(symbol, now_et, "symbol_not_found")

            # Get submissions (SEC API returns columnar format: dict of arrays)
            submissions = self.sec_client.get_submissions(cik)
            if not submissions:
                return self._unavailable_record(symbol, now_et, "no_submissions")

            # Extract columnar data from SEC API
            recent = submissions.get("filings", {}).get("recent", {})
            if not isinstance(recent, dict) or "form" not in recent:
                return self._unavailable_record(symbol, now_et, "invalid_submissions_format")

            forms = recent.get("form", [])
            dates = recent.get("filingDate", [])
            accessions = recent.get("accessionNumber", [])

            # Process each filing, building 8-K records from parallel arrays
            results = []
            for i, form in enumerate(forms[:100]):  # Limit to 100 most recent
                if form != "8-K":
                    continue

                filing_date_str = dates[i] if i < len(dates) else None
                if not filing_date_str:
                    continue

                filing_date = self._parse_date(filing_date_str)
                if filing_date < (since or date(1990, 1, 1)):
                    continue  # Skip filings before watermark

                accession_number = accessions[i] if i < len(accessions) else ""
                accession_number = accession_number.replace("-", "")

                try:
                    # Extract filing text (plaintext version of 8-K filing)
                    filing_text = self.sec_client.get_filing_plaintext(
                        cik, accession_number
                    )
                    items = self._extract_8k_items(filing_text)

                    # Extract summary from first 500 chars of filing
                    summary = filing_text[:500] if filing_text else ""

                except Exception as e:
                    logger.debug(f"[{symbol}] 8-K parsing error: {type(e).__name__}: {e}")
                    items = {}
                    summary = None

                record = {
                    "symbol": symbol,
                    "filing_date": filing_date,
                    "accession_number": accession_number,
                    "form_type": "8-K",
                    **items,
                    "event_summary": summary,
                    "material_items_text": None,
                    "data_unavailable": False,
                    "data_unavailable_reason": None,
                }

                results.append(record)

            return results

        except Exception as e:
            logger.error(f"[{symbol}] 8-K fetch error: {type(e).__name__}: {e}")
            now_et = datetime.now(EASTERN_TZ).date()
            return self._unavailable_record(
                symbol, now_et, f"fetch_error:{type(e).__name__}"
            )

    def _parse_date(self, date_str: str) -> date:
        """Parse SEC date string (YYYY-MM-DD format)."""
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return date.today()

    def _get_cik(self, symbol: str) -> str | None:
        """Get CIK for symbol from company_info_sec table."""
        try:
            from utils.db import DatabaseContext

            with DatabaseContext() as db:
                result = db.query(
                    "SELECT cik FROM company_info_sec WHERE symbol = %s LIMIT 1",
                    (symbol,),
                )
                if result and result[0]:
                    return str(result[0][0]).zfill(10)
        except Exception as e:
            logger.debug(f"[{symbol}] CIK lookup error: {e}")

        return None

    def _unavailable_record(self, symbol: str, measurement_date: date, reason: str) -> list[dict[str, Any]]:
        """Return a data_unavailable marker for this symbol."""
        return [
            {
                "symbol": symbol,
                "filing_date": measurement_date,
                "accession_number": "",
                "form_type": "8-K",
                "item_1_01": False,
                "item_1_02": False,
                "item_1_03": False,
                "item_2_01": False,
                "item_2_02": False,
                "item_2_03": False,
                "item_2_04": False,
                "item_2_05": False,
                "item_2_06": False,
                "item_2_07": False,
                "item_2_08": False,
                "item_3_01": False,
                "item_3_02": False,
                "item_3_03": False,
                "item_4_01": False,
                "item_4_02": False,
                "item_5_01": False,
                "item_5_02": False,
                "item_5_03": False,
                "item_5_05": False,
                "item_5_07": False,
                "item_6_01": False,
                "item_7_01": False,
                "item_8_01": False,
                "item_9_01": False,
                "event_summary": None,
                "material_items_text": None,
                "data_unavailable": True,
                "data_unavailable_reason": reason,
            }
        ]


def main() -> int:
    """Run the 8-K loader."""
    try:
        return run_loader(CurrentReports8KLoader)
    except Exception as e:
        logger.error(f"[8K FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
