#!/usr/bin/env python3
"""Dividend Data Loader - SEC EDGAR.

Loads dividend information from SEC filings including ex-dates, payment dates,
and dividend amounts. Used for position management and dividend tracking.

Data source: SEC EDGAR XBRL financial statements + 8-K filings
Update frequency: Daily (dividend events are reported as filed)

Dividend events are critical for:
- Dividend capture strategies
- Position management (hold through ex-date)
- Tax-efficient trading
- Portfolio yield calculation

Run:
    python3 loaders/load_dividend_data.py [--symbols AAPL,MSFT]
"""

import logging
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from loaders.helpers.sec_base import SecLoaderBase
from loaders.runner import run_loader
from loaders.timeout_config import configure_socket_timeout
from utils.external.sec_edgar import SecEdgarClient
from utils.infrastructure.timezone import EASTERN_TZ

logger = logging.getLogger(__name__)
configure_socket_timeout(30)


class DividendDataLoader(SecLoaderBase):
    """Load dividend data from SEC EDGAR.

    GOVERNANCE: Explicit data_unavailable pattern.
    This loader returns unavailable markers because required dividend data
    (ex-dividend dates, payment dates per SEC filings) is not yet integrated.

    TODO for future work:
    - Wire SEC 8-K Item 2.02 dividend announcements (declared dates + amounts)
    - Fetch dividend ex-dates from SEC XBRL companyfacts (if disclosed)
    - Implement Form 4 insider trading timeline correlation

    Until then, position management must use broker API for ex-date warnings.
    """

    table_name = "dividend_data"
    primary_key = ("symbol", "ex_dividend_date")
    watermark_field = "ex_dividend_date"
    exclude_etfs_from_symbols = True
    max_fail_rate = 3.0  # Some symbols may not have regular dividends

    def __init__(self, backfill_days: int | None = None):
        super().__init__(backfill_days)
        self.sec_client = SecEdgarClient()

    def _extract_dividend_from_xbrl(self, symbol: str) -> list[dict[str, Any]]:
        """Extract dividend information from XBRL financial statements.

        Looks for dividend declarations in 10-Q and 10-K filings.
        Only returns the most recent dividend payment per year to avoid duplicates.
        """
        try:
            from utils.db import DatabaseContext

            results = []

            # Query recent dividend declarations from SEC filings (up to 3 years)
            with DatabaseContext() as db:
                rows = db.query(
                    """
                    SELECT DISTINCT
                        fiscal_year, div_per_share_declared
                    FROM annual_income_statement
                    WHERE symbol = %s
                        AND div_per_share_declared IS NOT NULL
                        AND div_per_share_declared > 0
                        AND fiscal_year >= EXTRACT(YEAR FROM CURRENT_DATE) - 3
                    ORDER BY fiscal_year DESC
                    LIMIT 4
                    """,
                    (symbol,),
                )

                if rows:
                    for row in rows:
                        fiscal_year, div_per_share = row
                        # Estimate ex-date as end of fiscal year
                        ex_date = self._estimate_ex_date(fiscal_year, "FY")

                        results.append(
                            {
                                "symbol": symbol,
                                "declaration_date": None,
                                "ex_dividend_date": ex_date,
                                "record_date": None,
                                "payment_date": ex_date + timedelta(days=30),
                                "dividend_per_share": div_per_share,
                                "dividend_yield_pct": None,
                                "total_dividend_amount": None,
                                "dividend_type": "regular",
                                "currency": "USD",
                                "data_unavailable": False,
                                "data_unavailable_reason": None,
                                "source": "SEC_XBRL",
                            }
                        )

            return results

        except Exception as e:
            logger.debug(f"[{symbol}] XBRL dividend extraction error: {e}")
            return []

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch dividend data for symbol since given date.

        GOVERNANCE: Extract from official SEC 8-K Item 2.02 (Results of Operations).
        Dividend announcements are often disclosed in 8-K Item 2.02 sections.

        Returns: Dividend records extracted from 8-K filings, or data_unavailable marker.
        """
        try:
            # Get CIK for symbol
            cik = self.sec_client.symbol_to_cik(symbol)

            # Fetch submissions (SEC API returns columnar format)
            submissions = self.sec_client.get_submissions(cik)
            if not submissions:
                now_et = datetime.now(EASTERN_TZ).date()
                return self._unavailable_record(symbol, now_et, "no_submissions")

            # Extract 8-K filings
            recent = submissions.get("filings", {}).get("recent", {})
            if not isinstance(recent, dict) or "form" not in recent:
                now_et = datetime.now(EASTERN_TZ).date()
                return self._unavailable_record(symbol, now_et, "invalid_submissions_format")

            forms = recent.get("form", [])
            dates = recent.get("filingDate", [])
            accessions = recent.get("accessionNumber", [])

            results = []

            # Process 8-K filings looking for dividend announcements
            for i, form in enumerate(forms[:50]):  # Check last 50 filings
                if form != "8-K":
                    continue

                filing_date_str = dates[i] if i < len(dates) else None
                if not filing_date_str:
                    continue

                filing_date = self._parse_date(filing_date_str)
                if since and filing_date < since:
                    continue

                accession_number = accessions[i] if i < len(accessions) else ""
                accession_number = accession_number.replace("-", "")

                try:
                    # Extract filing text
                    filing_text = self.sec_client.get_filing_plaintext(cik, accession_number)
                    if not filing_text:
                        continue

                    # Extract Item 2.02 section (Results of Operations)
                    dividends = self._extract_dividends_from_8k(filing_text, filing_date)
                    # Add symbol to each dividend record
                    for div in dividends:
                        div["symbol"] = symbol
                    results.extend(dividends)

                except Exception as e:
                    logger.debug(f"[{symbol}] Error parsing 8-K {accession_number}: {e}")
                    continue

            if results:
                return results

            # No dividend announcements found
            now_et = datetime.now(EASTERN_TZ).date()
            return self._unavailable_record(symbol, now_et, "no_dividends_in_8k")

        except Exception as e:
            logger.debug(f"[{symbol}] Dividend fetch error: {e}")
            now_et = datetime.now(EASTERN_TZ).date()
            return self._unavailable_record(symbol, now_et, f"fetch_error:{type(e).__name__}")

    def _extract_dividends_from_8k(self, filing_text: str, filing_date: date) -> list[dict[str, Any]]:
        """Extract dividend announcements from 8-K Item 2.02 (Results of Operations).

        Item 2.02 often contains dividend declarations. This method:
        1. Finds Item 2.02 sections
        2. Searches for dividend keywords (declared, announced, paid, ex-date)
        3. Extracts dollar amounts and dates
        4. Returns structured dividend records
        """
        import re

        results = []
        text_upper = filing_text.upper()

        # Find Item 2.02 section (Results of Operations and Financial Condition)
        item_2_02_start = text_upper.find("ITEM 2.02")
        if item_2_02_start == -1:
            return results

        # Extract section up to next item or end of text
        next_item = len(filing_text)
        for item_num in ["2.03", "2.04", "2.05", "3.01", "4.01", "5.02", "8.01", "9.01"]:
            pos = text_upper.find(f"ITEM {item_num}", item_2_02_start + 10)
            if pos != -1 and pos < next_item:
                next_item = pos

        item_2_02_text = filing_text[item_2_02_start:next_item]

        # Search for dividend keywords
        dividend_keywords = ["dividend", "declared", "announced", "ex-date", "ex dividend", "payment date"]
        has_dividend = any(kw in item_2_02_text.lower() for kw in dividend_keywords)

        if not has_dividend:
            return results

        # Extract dividend per share amounts (e.g., "$0.23 per share")
        div_amount = self._extract_dividend_amount(item_2_02_text)
        if not div_amount:
            return results

        # Try to extract ex-date and payment date from text
        # Pattern: "ex-date of January 15, 2026" or "ex-dividend date: 1/15/2026"
        dates_found = self._extract_dates_from_text(item_2_02_text)

        if dates_found:
            # Use extracted dates
            for ex_date in dates_found:
                results.append(
                    {
                        "symbol": "",  # Will be filled in by caller
                        "declaration_date": filing_date,
                        "ex_dividend_date": ex_date,
                        "record_date": None,
                        "payment_date": ex_date + timedelta(days=3),  # Typical: 3 days after ex-date
                        "dividend_per_share": float(div_amount),
                        "dividend_yield_pct": None,
                        "total_dividend_amount": None,
                        "dividend_type": "regular",
                        "currency": "USD",
                        "data_unavailable": False,
                        "data_unavailable_reason": None,
                        "source": "SEC_8K_Item_2.02",
                    }
                )
        else:
            # If no specific dates found, estimate based on filing date
            # Dividends are typically ex'd within 1-3 months of announcement
            estimated_ex_date = filing_date + timedelta(days=45)
            results.append(
                {
                    "symbol": "",
                    "declaration_date": filing_date,
                    "ex_dividend_date": estimated_ex_date,
                    "record_date": None,
                    "payment_date": estimated_ex_date + timedelta(days=3),
                    "dividend_per_share": float(div_amount),
                    "dividend_yield_pct": None,
                    "total_dividend_amount": None,
                    "dividend_type": "regular",
                    "currency": "USD",
                    "data_unavailable": False,
                    "data_unavailable_reason": None,
                    "source": "SEC_8K_Item_2.02",
                }
            )

        return results

    def _extract_dates_from_text(self, text: str) -> list[date]:
        """Extract dates from text (ex-dates, payment dates, etc.)."""
        import re

        dates = []
        text_upper = text.upper()

        # Pattern 1: "ex-date of Month Day, Year" or "ex-dividend date: Month Day, Year"
        pattern1 = r"ex[- ](?:dividend )?date[:\s]+([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})"
        matches = re.finditer(pattern1, text, re.IGNORECASE)
        for match in matches:
            try:
                month_str, day_str, year_str = match.groups()
                from datetime import datetime as dt

                parsed = dt.strptime(f"{month_str} {day_str} {year_str}", "%B %d %Y").date()
                dates.append(parsed)
            except (ValueError, TypeError):
                pass

        # Pattern 2: "ex-date: MM/DD/YYYY" or "1/15/2026"
        pattern2 = r"ex[- ](?:dividend )?date[:\s]*(\d{1,2})[/-](\d{1,2})[/-](\d{4})"
        matches = re.finditer(pattern2, text, re.IGNORECASE)
        for match in matches:
            try:
                month_str, day_str, year_str = match.groups()
                from datetime import datetime as dt

                parsed = dt.strptime(f"{month_str}/{day_str}/{year_str}", "%m/%d/%Y").date()
                dates.append(parsed)
            except (ValueError, TypeError):
                pass

        # Remove duplicates and return
        return list(set(dates))

    def _parse_date(self, date_str: str) -> date:
        """Parse SEC date string (YYYY-MM-DD format)."""
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return date.today()

    def _estimate_ex_date(self, fiscal_year: int, fiscal_period: str) -> date:
        """Estimate ex-date from fiscal period."""
        # For quarterly earnings, estimate ex-date at end of fiscal quarter
        period_to_month = {"Q1": 3, "Q2": 6, "Q3": 9, "Q4": 12}
        month = period_to_month.get(fiscal_period, 12)
        return date(fiscal_year, month, 15)

    def _extract_dividend_amount(self, text: str) -> Decimal | None:
        """Try to extract dividend per share amount from text."""
        if not text:
            return None

        import re

        # Look for patterns like "$0.23 per share" or "0.23 dividend"
        patterns = [
            r"\$([0-9.]+)\s*(?:per share|dividend)",
            r"([0-9.]+)\s*(?:per share|dividend)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return Decimal(match.group(1))
                except (ValueError, TypeError):
                    pass

        return None

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
                "declaration_date": None,
                "ex_dividend_date": measurement_date,
                "record_date": None,
                "payment_date": None,
                "dividend_per_share": None,
                "dividend_yield_pct": None,
                "total_dividend_amount": None,
                "dividend_type": None,
                "currency": "USD",
                "data_unavailable": True,
                "data_unavailable_reason": reason,
                "source": "NONE",
            }
        ]


def main() -> int:
    """Run the dividend data loader."""
    try:
        return run_loader(DividendDataLoader)
    except Exception as e:
        logger.error(f"[DIVIDEND FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
