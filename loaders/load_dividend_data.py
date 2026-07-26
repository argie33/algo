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
    max_fail_rate = 100.0  # Dividend extraction not yet integrated; allow all data_unavailable markers

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

        GOVERNANCE: Fail-fast pattern with explicit data_unavailable marker.

        Dividend ex-dates and payment dates are critical for position management
        but require SEC Form 8-K Item 2.02 integration (dividend announcements)
        or SEC XBRL companyfacts (when filed). This implementation is incomplete.

        Returns: Explicit data_unavailable marker explaining the gap.
        """
        now_et = datetime.now(EASTERN_TZ).date()
        return self._unavailable_record(
            symbol,
            now_et,
            "sec_dividend_data_not_integrated",
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
