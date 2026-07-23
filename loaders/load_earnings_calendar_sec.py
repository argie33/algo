#!/usr/bin/env python3
"""Earnings Calendar Loader - SEC EDGAR + yfinance Fallback.

Primary: SEC EDGAR 10-K and 10-Q filing dates (authoritative, ~5% coverage)
Fallback: yfinance earnings dates (practical, ~80% coverage)

Strategy:
1. Try SEC EDGAR first (official, most reliable for recent filings)
2. Fall back to yfinance for symbols without recent SEC filings
3. Validates earnings dates within 24-month window only

Data source: SEC EDGAR submissions endpoint + yfinance API
Update frequency: As filings are made (annual + quarterly)

Run:
    python3 loaders/load_earnings_calendar_sec.py [--symbols AAPL,MSFT]
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
        self._yfinance_cache: dict[str, list[dict[str, Any]]] = {}

    def _fetch_from_yfinance(self, symbol: str, now_et: datetime) -> list[dict[str, Any]]:
        """Fallback: Fetch earnings dates from yfinance when SEC EDGAR has no recent data.

        yfinance provides estimated earnings dates with ~80% coverage across the universe.
        Used as fallback only when SEC filing data is unavailable.
        """
        try:
            import yfinance as yf

            try:
                ticker = yf.Ticker(symbol, session=None)
                info = ticker.info
            except Exception as e:
                logger.debug(f"[{symbol}] yfinance lookup failed: {type(e).__name__}")
                return self._unavailable_record(symbol, now_et, "yfinance_api_error")

            earnings_date_raw = info.get("earningsDate")
            if not earnings_date_raw:
                return self._unavailable_record(symbol, now_et, "yfinance_no_earnings_date")

            try:
                if isinstance(earnings_date_raw, (list, tuple)) and len(earnings_date_raw) > 0:
                    earnings_timestamp = earnings_date_raw[0]
                else:
                    earnings_timestamp = earnings_date_raw

                if isinstance(earnings_timestamp, int):
                    earnings_date = date.fromtimestamp(earnings_timestamp)
                elif isinstance(earnings_timestamp, date):
                    earnings_date = earnings_timestamp
                else:
                    logger.debug(f"[{symbol}] yfinance earningsDate has unexpected type: {type(earnings_timestamp)}")
                    return self._unavailable_record(symbol, now_et, "yfinance_invalid_date_type")

                if (now_et.date() - earnings_date).days > 730:
                    return self._unavailable_record(symbol, now_et, "yfinance_earnings_too_old")

                record = {
                    "symbol": symbol,
                    "filing_date": earnings_date,
                    "filing_type": "earnings_estimate",
                    "data_unavailable": False,
                    "reason": None,
                    "data_source": "yfinance_fallback",
                }
                return [record]
            except (ValueError, TypeError, AttributeError) as e:
                logger.debug(f"[{symbol}] yfinance date parse failed: {e}")
                return self._unavailable_record(symbol, now_et, "yfinance_date_parse_error")

        except ImportError:
            logger.warning("[yfinance] Module not available - cannot use fallback earnings source")
            return self._unavailable_record(symbol, now_et, "yfinance_not_installed")

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

            # Extract 10-K and 10-Q filing dates (these are the earnings-bearing
            # filing types; the SEC submissions feed also includes unrelated forms
            # like 8-K, S-4, and Form 4 which must be excluded here)
            for i, form_type in enumerate(forms):
                if form_type not in ("10-K", "10-Q"):
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
                            "filing_type": form_type,  # 10-K or 10-Q
                            "data_unavailable": False,
                            "reason": None,
                            "data_source": "sec_edgar_filings",
                        }
                        # Deduplicate by date: prefer 10-K over 10-Q (annual over quarterly)
                        if filing_date not in earnings_dates_dict:
                            earnings_dates_dict[filing_date] = (form_type, record)
                        elif form_type == "10-K" and earnings_dates_dict[filing_date][0] != "10-K":
                            # Replace with 10-K (higher priority)
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
                return earnings_dates

            # FALLBACK: No recent SEC filings found - try yfinance for practical coverage
            logger.debug(f"[{symbol}] No recent SEC filings found, trying yfinance fallback")
            return self._fetch_from_yfinance(symbol, now_et)

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
