#!/usr/bin/env python3
"""Earnings Calendar Loader - SEC EDGAR Filing Dates.

PHASE 3 OPTIMIZATION (Session 237):
Replaces yfinance earnings dates (~10% of yfinance_snapshot) with
authoritative SEC EDGAR 10-K and 10-Q filing dates.

Data source: SEC EDGAR submissions endpoint (10-K annual, 10-Q quarterly filings)
Update frequency: As filings are made (annual + quarterly)
Quality: Official SEC filing dates > yfinance estimates

Earnings calendar:
- 10-K: Annual report (earnings announcement after filing)
- 10-Q: Quarterly report (earnings announcement after filing)
- Filing dates are when earnings are officially announced to SEC

Run:
    python3 loaders/load_earnings_calendar_sec.py [--symbols AAPL,MSFT]
"""

import logging
import sys
from datetime import date, datetime
from typing import Any

from loaders.helpers.sec_base import SecLoaderBase
from loaders.runner import run_loader
from loaders.timeout_config import configure_socket_timeout
from utils.external.sec_edgar import SecEdgarClient
from utils.infrastructure.timezone import EASTERN_TZ
from utils.loaders.exception_handler import handle_exception, handle_invalid_data

logger = logging.getLogger(__name__)
configure_socket_timeout(30)


class EarningsCalendarSECLoader(SecLoaderBase):
    """Load earnings calendar from SEC EDGAR.

    PHASE 3: Eliminates yfinance earnings_date (~10% yfinance load).
    Uses SEC EDGAR submissions endpoint which provides 10-K (annual) and
    10-Q (quarterly) filing dates. These are the official earnings announcements.

    Benefits:
    - Official SEC filing dates (authoritative)
    - Quarterly + annual coverage
    - Direct API access (no parsing required)
    - Eliminates yfinance rate-limiting dependency

    Trade-off: Filing dates lag slightly behind earnings announcements
    (typically announced after market close; SEC filing within 60-90 days).
    Acceptable for stock scoring (not real-time trading).
    """

    table_name = "earnings_calendar_sec"
    primary_key = ("symbol", "filing_date")
    watermark_field = "filing_date"
    exclude_etfs_from_symbols = True

    def __init__(self, backfill_days: int | None = None):
        super().__init__(backfill_days)
        self.sec_client = SecEdgarClient()

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch earnings dates from SEC EDGAR submissions API.

        Extracts 10-K (annual) and 10-Q (quarterly) filing dates which
        correspond to earnings announcements.

        Args:
            symbol: Stock ticker symbol
            since: Minimum filing date to fetch (for incremental updates)

        Returns:
            List with earnings records or data_unavailable marker
        """
        now_et = datetime.now(EASTERN_TZ)

        try:
            # Convert symbol to CIK
            try:
                cik = self.sec_client.symbol_to_cik(symbol)
            except ValueError:
                logger.warning(f"[{symbol}] CIK not found in SEC ticker cache")
                return self._unavailable_record(symbol, now_et, "cik_not_found")

            # Fetch submissions which has filing dates
            try:
                submissions = self.sec_client.get_submissions(cik)
            except FileNotFoundError:
                return self._unavailable_record(symbol, now_et, "submissions_not_found_404")

            if not submissions:
                return self._unavailable_record(symbol, now_et, "submissions_empty")

            # EXPLICIT: Validate SEC API response structure (fail-fast if schema changes)
            if "filings" not in submissions:
                logger.warning(f"[{symbol}] SEC API submissions missing 'filings' key (structure may have changed)")
                return self._unavailable_record(symbol, now_et, "filings_key_missing")

            filings_obj = submissions["filings"]
            if not isinstance(filings_obj, dict) or "recent" not in filings_obj:
                logger.debug(f"[{symbol}] SEC API filings missing 'recent' key")
                return self._unavailable_record(symbol, now_et, "recent_filings_key_missing")

            recent_filings = filings_obj["recent"]

            if "form" not in recent_filings or "filingDate" not in recent_filings:
                logger.debug(f"[{symbol}] SEC recent filings missing 'form' or 'filingDate' keys")
                return self._unavailable_record(symbol, now_et, "recent_filings_missing_keys")

            forms = recent_filings["form"]
            filing_dates = recent_filings["filingDate"]

            # Validate arrays are same length (data integrity check)
            if len(forms) != len(filing_dates):
                logger.error(
                    f"[{symbol}] SEC API data corruption: forms array ({len(forms)} items) != "
                    f"filing_dates array ({len(filing_dates)} items). Cannot process."
                )
                return self._unavailable_record(symbol, now_et, "array_length_mismatch")

            earnings_dates = []

            # Extract 10-K and 10-Q filing dates
            for i, form_type in enumerate(forms):
                try:
                    filing_date_str = filing_dates[i]
                    # Validate filing date format (ISO format expected)
                    try:
                        filing_date = datetime.fromisoformat(filing_date_str).date()
                    except (ValueError, TypeError) as e:
                        # Skip this specific record - invalid date format in API response
                        logger.debug(
                            f"[{symbol}] Skipping filing at index {i}: invalid date format '{filing_date_str}': {e}"
                        )
                        continue

                    # Only include recent filings (last 24 months)
                    if (now_et.date() - filing_date).days <= 730:
                        earnings_dates.append(
                            {
                                "symbol": symbol,
                                "filing_date": filing_date,
                                "filing_type": form_type,  # 10-K or 10-Q
                                "data_unavailable": False,
                                "reason": None,
                            }
                        )
                except IndexError as e:
                    # Array index mismatch (shouldn't happen due to earlier validation)
                    logger.error(
                        f"[{symbol}] Array index error at position {i}: {e}. "
                        "This suggests data corruption in SEC API response."
                    )
                    break

            if not earnings_dates:
                return self._unavailable_record(symbol, now_et, "no_recent_earnings_filings")

            # Return most recent filings first
            earnings_dates.sort(key=lambda x: x["filing_date"], reverse=True)

            return earnings_dates

        except TimeoutError as e:
            marker = handle_exception(symbol, e, "fetching earnings calendar")
            return [marker]
        except KeyError as e:
            marker = handle_exception(symbol, e, "SEC API missing required fields")
            return [marker]
        except Exception as e:
            # Try to handle via classification, or fail-fast if unexpected
            try:
                marker = handle_exception(symbol, e, "fetching earnings calendar")
                return [marker]
            except Exception:
                logger.critical(f"[{symbol}] Failed to fetch earnings calendar: {type(e).__name__}: {e}", exc_info=True)
                raise

    def _unavailable_record(self, symbol: str, now_et: datetime, reason: str) -> list[dict[str, Any]]:
        """Helper to create a data_unavailable record."""
        return [
            {
                "symbol": symbol,
                "filing_date": now_et.date(),
                "filing_type": None,
                "data_unavailable": True,
                "reason": reason,
            }
        ]


def main() -> int:
    """Entry point for load_earnings_calendar_sec.py."""
    try:
        return run_loader(EarningsCalendarSECLoader)
    except Exception as e:
        logger.error(f"[EARNINGS_CALENDAR FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
