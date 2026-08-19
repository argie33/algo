#!/usr/bin/env python3
"""Earnings Calendar Loader - SEC EDGAR only, no yfinance fallback.

Source: SEC EDGAR 10-K and 10-Q filing dates (authoritative).

Strategy:
1. Fetch 10-K/10-Q filing dates from SEC EDGAR submissions
2. Validates earnings dates within 24-month window only
3. Fails fast (data_unavailable) when no recent SEC filings exist - see the
   Session 416 fail-fast note in fetch_incremental for why a yfinance fallback
   was removed rather than kept as a secondary source.

Data source: SEC EDGAR submissions endpoint
Update frequency: As filings are made (annual + quarterly)

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
from utils.db.context import DatabaseContext
from utils.external.sec_edgar import SecEdgarClient
from utils.infrastructure.timezone import EASTERN_TZ
from utils.loaders.exception_handler import handle_exception

logger = logging.getLogger(__name__)
configure_socket_timeout(30)

# FIXED 2026-08-19 ("no SEC data"/loader audit): only "10-K"/"10-Q" were ever accepted -
# foreign private issuers file 20-F (annual, not 10-K) and 6-K (interim, not 10-Q) instead,
# and Canadian MJDS filers file 40-F. This is the same gap already fixed for
# current_reports_8k.py (foreign filers use 6-K, not 8-K) and load_company_info_sec.py's
# has_annual_report_filing check. Live-confirmed via the real SEC API: ABEV (Ambev) has 12
# real 20-F + 863 6-K filings and zero 10-K/10-Q, AEG (Aegon) 21 20-F + 650 6-K, AG (First
# Majestic Silver) 16 40-F + 419 6-K - all real, well-known companies that filed
# "no_sec_filings_found" despite having a complete, real filing history. 1,203 universe
# symbols affected. Matches the "earnings-bearing" form set already established in
# utils/external/sec_statements.py's _PRIMARY_STATEMENT_FORMS for the identical distinction.
_EARNINGS_BEARING_FORMS = frozenset(
    {
        "10-K",
        "10-K/A",
        "10-KT",
        "10-KT/A",
        "10-Q",
        "10-Q/A",
        "10-QT",
        "10-QT/A",
        "20-F",
        "20-F/A",
        "40-F",
        "40-F/A",
        "6-K",
        "6-K/A",
    }
)

# The annual-report subset of _EARNINGS_BEARING_FORMS above, used to prioritize an annual
# filing over an interim one when both land on the same date (rare, but the same "prefer
# 10-K over 10-Q" priority this loader already had before foreign forms were added).
_ANNUAL_FILING_FORMS = frozenset({"10-K", "10-K/A", "10-KT", "10-KT/A", "20-F", "20-F/A", "40-F", "40-F/A"})


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
    max_fail_rate = 2.0  # SEC API occasionally fails on isolated symbols

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
                logger.warning(f"[{symbol}] SEC API filings missing 'recent' key")
                return self._unavailable_record(symbol, now_et, "recent_filings_key_missing")

            recent_filings = filings_obj["recent"]

            if "form" not in recent_filings or "filingDate" not in recent_filings:
                logger.warning(f"[{symbol}] SEC recent filings missing 'form' or 'filingDate' keys")
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

            earnings_dates_dict = {}  # Key: filing_date, Value: (filing_type, record)

            # Extract annual/quarterly-equivalent filing dates (these are the earnings-bearing
            # filing types, domestic and foreign alike; the SEC submissions feed also includes
            # unrelated forms like 8-K, S-4, and Form 4 which must be excluded here)
            for i, form_type in enumerate(forms):
                if form_type not in _EARNINGS_BEARING_FORMS:
                    continue
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
                        record = {
                            "symbol": symbol,
                            "filing_date": filing_date,
                            "filing_type": form_type,  # 10-K/20-F/40-F (annual) or 10-Q/6-K (interim)
                            "data_unavailable": False,
                            "reason": None,
                            "data_source": "sec_edgar_filings",
                        }
                        # Deduplicate by date: prefer the annual-report form over the
                        # interim form (10-K/20-F/40-F outrank 10-Q/6-K), same "annual over
                        # quarterly" priority as before, now covering foreign filers too.
                        is_annual = form_type in _ANNUAL_FILING_FORMS
                        if filing_date not in earnings_dates_dict:
                            earnings_dates_dict[filing_date] = (form_type, record)
                        elif is_annual and earnings_dates_dict[filing_date][0] not in _ANNUAL_FILING_FORMS:
                            # Replace with the annual-report form (higher priority)
                            earnings_dates_dict[filing_date] = (form_type, record)
                except IndexError as e:
                    # Array index mismatch (shouldn't happen due to earlier validation)
                    logger.error(
                        f"[{symbol}] Array index error at position {i}: {e}. "
                        "This suggests data corruption in SEC API response."
                    )
                    break

            if earnings_dates_dict:
                # Convert dict values back to list and sort by date (most recent first)
                earnings_dates = [record for _, (_, record) in earnings_dates_dict.items()]
                earnings_dates.sort(key=lambda x: x["filing_date"], reverse=True)
                # FIXED 2026-08-19 ("no SEC data"/loader audit, foreign-filer-forms follow-up):
                # a symbol that WAS genuinely unavailable in an earlier run (marker written via
                # _unavailable_record, filing_date = the date that run happened, primary_key
                # (symbol, filing_date) so it's a separate row from any real filing) keeps that
                # marker forever once real data starts arriving - a normal INSERT/UPSERT of the
                # real rows below has a different primary key and never touches it. Since the
                # marker's filing_date is "the day the loader ran", not a real filing date, it
                # can easily sort AFTER every real filing_date in a naive "ORDER BY filing_date
                # DESC LIMIT 1" read, permanently masking the real data that just arrived. Live-
                # confirmed via AEG right after the 20-F/40-F/6-K form-recognition fix landed:
                # a stale marker dated 2026-07-21 (this loader's last pre-fix run) outranked
                # AEG's real, correct 2026-07-01 6-K filing. 269 universe symbols hit this exact
                # collision. Delete any leftover marker now that real data has arrived - same
                # "clean up the now-superseded marker" principle already applied elsewhere in
                # this codebase for event-log tables.
                with DatabaseContext("write") as cur:
                    cur.execute(
                        "DELETE FROM earnings_calendar_sec WHERE symbol = %s AND data_unavailable = true",
                        (symbol,),
                    )
                return earnings_dates

            # CRITICAL FIX (Session 416): Removed yfinance fallback per GOVERNANCE fail-fast principle.
            # When SEC filing data unavailable, fail-fast instead of silently substituting secondary source.
            # Reason: Operators cannot distinguish official SEC filings from yfinance estimates;
            # this violates data integrity and operator visibility requirements.
            # See GOVERNANCE.md line 55-58: "No secondary fallbacks. Never use yfinance beta instead of calculated volatility"
            logger.warning(
                f"[{symbol}] No recent SEC filings found. "
                f"ROOT CAUSE: Symbol may have no recent annual filings (REITs, IPOs, delisted stocks). "
                f"ACTION: Check SEC Edgar directly or verify symbol is active. "
                f"Cannot proceed with earnings calendar data."
            )
            return self._unavailable_record(symbol, now_et, "no_sec_filings_found")

        except TimeoutError as e:
            marker = handle_exception(symbol, e, "fetching earnings calendar")
            return [marker]
        except KeyError as e:
            marker = handle_exception(symbol, e, "SEC API missing required fields")
            return [marker]
        except Exception as e:
            # Try to handle via classification, or fail-fast if unexpected
            return self._wrap_exception_handler(symbol, e, "fetching earnings calendar")

    def _unavailable_record(self, symbol: str, now_et: datetime, reason: str) -> list[dict[str, Any]]:
        """Helper to create a data_unavailable record.

        Reuses the filing_date of any existing unavailable marker for this symbol
        instead of always stamping today's date. primary_key is (symbol, filing_date),
        so stamping "today" here would insert a brand-new row every day this symbol
        has no recent filings, growing the table unbounded (same bug class fixed in
        company_info_sec/institutional_holdings_13f/insider_holdings_sec).
        """
        from utils.db.context import DatabaseContext

        filing_date = now_et.date()
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT filing_date FROM earnings_calendar_sec "
                    "WHERE symbol = %s AND data_unavailable = true LIMIT 1",
                    (symbol,),
                )
                existing = cur.fetchone()
                if existing:
                    filing_date = existing[0]
        except Exception as e:
            logger.warning(f"[{symbol}] Failed to look up existing unavailable marker: {e}")

        return [
            {
                "symbol": symbol,
                "filing_date": filing_date,
                "filing_type": None,
                "data_unavailable": True,
                "reason": reason,
                "data_source": "none",
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
