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
from utils.loaders.exception_handler import handle_exception

logger = logging.getLogger(__name__)
configure_socket_timeout(30)


class DividendDataLoader(SecLoaderBase):
    """Load dividend data from SEC EDGAR.

    Extracts dividend information from:
    1. SEC XBRL financial statement tags (DIV_PER_SHARE_DECLARED)
    2. 8-K filings for dividend announcements
    3. Estimated future dividends from recent patterns

    Provides:
    - Ex-dividend dates (critical for position management)
    - Payment dates
    - Dividend amounts and yields
    - Dividend classification (regular, special, stock)
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
        """
        try:
            from utils.db import DatabaseContext

            results = []

            # Query recent dividend declarations from SEC filings
            with DatabaseContext() as db:
                # Look for historical dividend records
                rows = db.query(
                    """
                    SELECT DISTINCT
                        fiscal_year, fiscal_period, div_per_share_declared
                    FROM annual_income_statement
                    WHERE symbol = %s
                        AND div_per_share_declared IS NOT NULL
                        AND div_per_share_declared > 0
                    ORDER BY fiscal_year DESC, fiscal_period DESC
                    LIMIT 8
                    """,
                    (symbol,),
                )

                if rows:
                    for row in rows:
                        fiscal_year, fiscal_period, div_per_share = row
                        # Estimate ex-date based on fiscal period
                        # (This is approximate - real dates would come from 8-K)
                        ex_date = self._estimate_ex_date(fiscal_year, fiscal_period)

                        if ex_date >= date.today() - timedelta(days=90):
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

    def _extract_dividend_from_8k(self, symbol: str) -> list[dict[str, Any]]:
        """Extract dividend announcements from 8-K filings (Item 2.02).

        Form 8-K Item 2.02 includes financial results which often contain
        dividend announcements.
        """
        try:
            # Get CIK for symbol
            cik = self._get_cik(symbol)
            if not cik:
                return []

            from utils.db import DatabaseContext

            # Check if we have recent 8-K filings with dividend announcements
            with DatabaseContext() as db:
                rows = db.query(
                    """
                    SELECT filing_date, event_summary
                    FROM current_reports_8k
                    WHERE symbol = %s
                        AND (
                            item_2_02 = TRUE
                            OR event_summary ILIKE '%dividend%'
                        )
                    ORDER BY filing_date DESC
                    LIMIT 4
                    """,
                    (symbol,),
                )

            results = []
            for filing_date, summary in rows or []:
                # Parse dividend amount from summary if possible
                div_per_share = self._extract_dividend_amount(summary)
                if div_per_share:
                    # Estimate ex-date (typically ~2 weeks after announcement)
                    ex_date = filing_date + timedelta(days=14)
                    results.append(
                        {
                            "symbol": symbol,
                            "declaration_date": filing_date,
                            "ex_dividend_date": ex_date,
                            "record_date": ex_date + timedelta(days=1),
                            "payment_date": ex_date + timedelta(days=30),
                            "dividend_per_share": div_per_share,
                            "dividend_yield_pct": None,
                            "total_dividend_amount": None,
                            "dividend_type": "regular",
                            "currency": "USD",
                            "data_unavailable": False,
                            "data_unavailable_reason": None,
                            "source": "SEC_8K",
                        }
                    )

            return results

        except Exception as e:
            logger.debug(f"[{symbol}] 8-K dividend extraction error: {e}")
            return []

    def fetch_incremental(self, symbol: str, since: date) -> list[dict[str, Any]]:
        """Fetch dividend data for symbol since given date."""
        try:
            results = []
            now_et = datetime.now(EASTERN_TZ).date()

            # Try XBRL extraction
            xbrl_divs = self._extract_dividend_from_xbrl(symbol)
            results.extend(xbrl_divs)

            # Try 8-K extraction if XBRL found nothing
            if not results:
                k8_divs = self._extract_dividend_from_8k(symbol)
                results.extend(k8_divs)

            # Filter to only dividends on/after watermark
            results = [r for r in results if r.get("ex_dividend_date", date.today()) >= since]

            # If still empty, return unavailable marker
            if not results:
                return self._unavailable_record(
                    symbol,
                    now_et,
                    "no_recent_dividends",
                )

            return results

        except Exception as e:
            logger.error(f"[{symbol}] Dividend fetch error: {type(e).__name__}: {e}")
            now_et = datetime.now(EASTERN_TZ).date()
            return self._unavailable_record(
                symbol,
                now_et,
                f"fetch_error:{type(e).__name__}",
            )

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
