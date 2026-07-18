#!/usr/bin/env python3
"""Insider Holdings Loader - SEC Form 4/5 (Near Real-Time).

PHASE 2 OPTIMIZATION (Session 237):
Replaces yfinance held_percent_insiders (~15% of yfinance_snapshot) with
authoritative SEC Form 4/5 insider transaction data (2-day lag).

Data source: SEC EDGAR Form 4/5 filings (insider transactions, near real-time)
Update frequency: 2-day lag (regulatory filing deadline)
Quality: Official SEC insider transactions > yfinance estimates

Insider holdings computed from Form 4 transactions:
- Form 4: Insider transactions (officers, directors, 10%+ owners)
- Form 5: Annual filings for remaining insider holdings
- Data lag: 2 days (Form 4 filed within 2 days of transaction)

Run:
    python3 loaders/load_insider_holdings_sec.py [--symbols AAPL,MSFT]
"""

import logging
import sys
from datetime import date, datetime, timedelta
from typing import Any

from loaders.helpers.sec_base import SecLoaderBase
from loaders.runner import run_loader
from loaders.timeout_config import configure_socket_timeout
from utils.external.sec_edgar import SecEdgarClient
from utils.external.sec_xml_parser import Form4Parser
from utils.infrastructure.timezone import EASTERN_TZ

logger = logging.getLogger(__name__)
configure_socket_timeout(30)


class InsiderHoldingsSECLoader(SecLoaderBase):
    """Load insider holdings from SEC Form 4/5 filings.

    PHASE 2: Eliminates yfinance held_percent_insiders (~15% yfinance load).
    Uses SEC Form 4/5 insider transactions (2-day lag, near real-time).

    Benefits:
    - Official SEC insider filings (regulatory authority)
    - Near real-time updates (2-day lag)
    - Granular transaction tracking (can see buy/sell patterns)
    - Eliminates yfinance rate-limiting dependency

    Trade-off: 2-day lag (acceptable for monitoring; real-time needs paid service).

    Implementation (Session 237):
    - Fetches Form 4/5 filings from SEC EDGAR submissions API
    - Parses insider transaction data from filings
    - Aggregates insider holdings and recent buy/sell activity
    - Computes insider ownership % and activity metrics
    """

    table_name = "insider_holdings_sec"
    primary_key = ("symbol", "filing_date")
    watermark_field = "filing_date"
    exclude_etfs_from_symbols = True

    def __init__(self, backfill_days: int | None = None):
        super().__init__(backfill_days)
        self.sec_client = SecEdgarClient()

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch insider holdings from SEC Form 4/5 filings.

        Fetches recent Form 4 filings, extracts insider transaction data,
        aggregates holdings and activity metrics.

        Args:
            symbol: Stock ticker symbol
            since: Minimum filing date to fetch (for incremental updates)

        Returns:
            List with insider holdings record or data_unavailable marker
        """
        now_et = datetime.now(EASTERN_TZ)

        try:
            # Get CIK for this symbol
            try:
                cik = self.sec_client.symbol_to_cik(symbol)
            except ValueError:
                logger.warning(f"[{symbol}] CIK not found in SEC ticker cache")
                return self._unavailable_record(symbol, now_et, "cik_not_found")

            # Fetch submissions to find Form 4 filings
            try:
                submissions = self.sec_client.get_submissions(cik)
            except FileNotFoundError:
                return self._unavailable_record(symbol, now_et, "submissions_not_found_404")

            # Extract Form 4 filings from recent filings (fail-fast if structure wrong)
            if "filings" not in submissions:
                return self._unavailable_record(symbol, now_et, "invalid_submissions_structure:missing_filings")
            if "recent" not in submissions["filings"]:
                return self._unavailable_record(symbol, now_et, "invalid_submissions_structure:missing_recent")

            recent_filings = submissions["filings"]["recent"]
            if "form" not in recent_filings or "accessionNumber" not in recent_filings or "filingDate" not in recent_filings:
                return self._unavailable_record(symbol, now_et, "invalid_filings_structure:missing_required_fields")

            forms = recent_filings["form"]
            accession_numbers = recent_filings["accessionNumber"]
            filing_dates = recent_filings["filingDate"]

            form_4_filings = []
            for i, form_type in enumerate(forms):
                if form_type == "4" and i < len(accession_numbers):
                    accession = accession_numbers[i]
                    filing_date_str = filing_dates[i] if i < len(filing_dates) else None
                    if filing_date_str:
                        try:
                            filing_date_obj = datetime.fromisoformat(filing_date_str).date()
                            # Only fetch recent filings (last 90 days)
                            if (now_et.date() - filing_date_obj).days <= 90:
                                form_4_filings.append((accession, filing_date_obj))
                        except (ValueError, TypeError):
                            pass

            if not form_4_filings:
                return self._unavailable_record(symbol, now_et, "no_recent_form4_filings")

            # Parse Form 4 filings to extract insider transaction data
            return self._parse_form4_filings(symbol, cik, form_4_filings, now_et)

        except Exception as e:
            logger.error(f"[{symbol}] Failed to fetch insider holdings: {type(e).__name__}: {e}")
            return self._unavailable_record(symbol, now_et, f"fetch_error: {str(e)[:40]}")

    def _parse_form4_filings(
        self,
        symbol: str,
        cik: str,
        filings: list[tuple[str, date]],
        now_et: datetime,
    ) -> list[dict[str, Any]]:
        """Parse Form 4 filings to extract insider transaction data.

        Fetches and parses Form 4 XML documents to extract:
        - Insider holdings (current share count and % ownership)
        - Recent buy/sell activity (90-day window)
        - Latest transaction date

        Args:
            symbol: Stock ticker
            cik: Company CIK
            filings: List of (accession_number, filing_date) tuples
            now_et: Current datetime

        Returns:
            List with insider holdings record or data_unavailable marker
        """
        # Aggregate data across all recent Form 4 filings
        aggregated_insiders: dict[str, dict[str, Any]] = {}
        latest_filing_date = None

        for accession_number, filing_date in filings:
            try:
                # Fetch Form 4 XML from SEC EDGAR
                xml_content = self.sec_client.get_filing_xml(cik, accession_number, "4")

                # Parse XML to extract insider data
                parsed_data = Form4Parser.parse(xml_content, symbol)

                # Track latest filing date
                if latest_filing_date is None or filing_date > latest_filing_date:
                    latest_filing_date = filing_date

                # Fail-fast: required fields must be present in parsed data
                required_fields = ["insider_name", "shares_owned", "ownership_pct", "recent_buys", "recent_sells", "net_transactions"]
                missing_fields = [f for f in required_fields if f not in parsed_data or parsed_data[f] is None]
                if missing_fields:
                    logger.warning(f"[{symbol}] Form 4 XML missing required fields: {missing_fields}")
                    continue

                # Aggregate insider data (use insider name as key)
                insider_key = parsed_data["insider_name"]
                if insider_key not in aggregated_insiders:
                    aggregated_insiders[insider_key] = {
                        "name": parsed_data["insider_name"],
                        "title": parsed_data.get("insider_title"),
                        "shares_owned": parsed_data["shares_owned"],
                        "ownership_pct": parsed_data["ownership_pct"],
                        "buys": parsed_data["recent_buys"],
                        "sells": parsed_data["recent_sells"],
                        "net_txns": parsed_data["net_transactions"],
                    }
                else:
                    # Aggregate counts across multiple filings
                    aggregated_insiders[insider_key]["buys"] += parsed_data["recent_buys"]
                    aggregated_insiders[insider_key]["sells"] += parsed_data["recent_sells"]
                    aggregated_insiders[insider_key]["net_txns"] += parsed_data["net_transactions"]

            except FileNotFoundError:
                logger.warning(f"[{symbol}] Form 4 XML not found for accession {accession_number}")
                continue
            except ValueError as e:
                logger.warning(f"[{symbol}] Failed to parse Form 4 XML for accession {accession_number}: {e}")
                continue
            except Exception as e:
                logger.warning(f"[{symbol}] Error fetching Form 4 for accession {accession_number}: {e}")
                continue

        # If we successfully parsed any Form 4 filings, compute aggregate statistics
        if aggregated_insiders:
            # Aggregate across all insiders
            total_insider_transactions = sum(i["buys"] + i["sells"] for i in aggregated_insiders.values())
            net_aggregate_transactions = sum(i["net_txns"] for i in aggregated_insiders.values())

            # Use the most recent Form 4's ownership % and share count as representative
            latest_insider = next(iter(aggregated_insiders.values()))

            # Validate that ownership_pct is valid before returning
            ownership_pct = latest_insider["ownership_pct"]
            if not isinstance(ownership_pct, (int, float)) or ownership_pct is None:
                return self._unavailable_record(symbol, now_et, f"invalid_insider_ownership_pct:{ownership_pct}")

            return [
                {
                    "symbol": symbol,
                    "filing_date": latest_filing_date or now_et.date(),
                    "insider_ownership_pct": float(ownership_pct),
                    "number_of_insiders": len(aggregated_insiders),
                    "recent_buys": sum(i["buys"] for i in aggregated_insiders.values()),
                    "recent_sells": sum(i["sells"] for i in aggregated_insiders.values()),
                    "net_insider_transactions": net_aggregate_transactions,
                    "data_unavailable": False,
                    "reason": None,
                    "latest_insider_filing_date": latest_filing_date,
                    "sec_filing_url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=4&dateb=&owner=exclude",
                }
            ]

        # No valid Form 4 filings found
        return self._unavailable_record(symbol, now_et, "form4_parsing_failed_all_filings")

    def _unavailable_record(self, symbol: str, now_et: datetime, reason: str) -> list[dict[str, Any]]:
        """Helper to create a data_unavailable record."""
        return [
            {
                "symbol": symbol,
                "filing_date": now_et.date(),
                "insider_ownership_pct": None,
                "number_of_insiders": None,
                "recent_buys": None,
                "recent_sells": None,
                "net_insider_transactions": None,
                "data_unavailable": True,
                "reason": reason,
                "latest_insider_filing_date": None,
                "sec_filing_url": None,
            }
        ]


def main() -> int:
    """Entry point for load_insider_holdings_sec.py."""
    try:
        return run_loader(InsiderHoldingsSECLoader)
    except Exception as e:
        logger.error(f"[INSIDER_SEC FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
