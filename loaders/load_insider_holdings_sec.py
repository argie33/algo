#!/usr/bin/env python3
"""Insider Holdings Loader - SEC Form 3/4/5 via official bulk data sets.

GOVERNANCE: No yfinance fallback. Only official SEC sources or explicit
data_unavailable.

Uses utils.external.sec_form345_bulk.Form345BulkAggregator, which downloads
SEC's own pre-flattened quarterly "Insider Transactions Data Sets"
(sec.gov/data-research/sec-markets-data/insider-transactions-data-sets)
instead of crawling each insider's Form 4 XML individually. That per-filing
approach was investigated in Session 298 and estimated at 8-16h / tens of
thousands of requests against EDGAR's 2 req/s rate limit - infeasible. The
bulk data sets contain the identical SEC-sourced facts (same
SHRS_OWND_FOLWNG_TRANS field used by the per-filing XML), pre-joined by
issuer ticker, with no rate-limit wall: a handful of quarterly ZIP downloads
instead of one HTTP request per filing. See sec_form345_bulk.py's docstring
for the full aggregation methodology.

Run:
    python3 loaders/load_insider_holdings_sec.py [--symbols AAPL,MSFT]
"""

import logging
import sys
from datetime import date, datetime
from typing import Any

from loaders.runner import run_loader
from loaders.timeout_config import configure_socket_timeout
from utils.db.context import DatabaseContext
from utils.external.sec_form345_bulk import Form345BulkAggregator
from utils.infrastructure.timezone import EASTERN_TZ
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)
configure_socket_timeout(30)


class InsiderHoldingsSECLoader(OptimalLoader):
    """Load insider ownership % from SEC's official Form 3/4/5 bulk data sets.

    GOVERNANCE: No yfinance fallback. Only official SEC sources or explicit
    data_unavailable.
    """

    table_name = "insider_holdings_sec"
    # symbol-only: this is a current-snapshot table (one row per symbol), not a real
    # historical time series - filing_date gets set to "today" on every run since the
    # source is always data_unavailable, so a compound key here just accumulates a
    # fresh duplicate row forever instead of updating in place (fixed by migration 1124).
    primary_key = ("symbol",)
    watermark_field = "filing_date"
    exclude_etfs_from_symbols = True

    def __init__(self, backfill_days: int | None = None):
        super().__init__(backfill_days)
        # Built lazily on first fetch_incremental() call, shared across all worker
        # threads in this run (thread-safe, builds exactly once - see
        # Form345BulkAggregator docstring).
        self._aggregator = Form345BulkAggregator()

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch insider ownership from SEC's bulk Form 3/4/5 data sets.

        Args:
            symbol: Stock ticker symbol
            since: Unused - the bulk aggregate is a point-in-time snapshot rebuilt
                fresh each run from SEC's latest published quarters, not an
                incremental feed.

        Returns:
            List with insider holdings record, or a data_unavailable marker if the
            symbol had no Form 3/4/5 filings in the lookback window or its
            shares_outstanding is unknown (can't compute a percentage).
        """
        now_et = datetime.now(EASTERN_TZ)

        summary = self._aggregator.get_symbol_summary(symbol)
        if summary is None:
            return self._unavailable_record(symbol, now_et, "no_form345_filings_in_lookback_window")

        shares_outstanding = self._get_shares_outstanding(symbol)
        if not shares_outstanding:
            return self._unavailable_record(symbol, now_et, "shares_outstanding_unavailable_for_pct_calc")

        insider_pct = min((summary.total_shares / shares_outstanding) * 100.0, 100.0)

        return [
            {
                "symbol": symbol,
                "filing_date": now_et.date(),
                "insider_ownership_pct": round(insider_pct, 4),
                "number_of_insiders": summary.number_of_insiders,
                "recent_buys": summary.recent_buys,
                "recent_sells": summary.recent_sells,
                "net_insider_transactions": summary.recent_buys - summary.recent_sells,
                "data_unavailable": False,
                "reason": None,
                "latest_insider_filing_date": summary.latest_filing_date,
                "sec_filing_url": summary.sec_filing_url,
                "data_source": "sec_form345_bulk",
                "updated_at": now_et,
            }
        ]

    @staticmethod
    def _get_shares_outstanding(symbol: str) -> int | None:
        with DatabaseContext("read") as cur:
            # NOTE: Removed data_unavailable = FALSE filter to allow fetching shares_outstanding
            # even if company_info_sec is marked unavailable for other reasons.
            # We only care about the shares_outstanding value, not the overall unavailable flag.
            cur.execute(
                """
                SELECT shares_outstanding
                FROM company_info_sec
                WHERE symbol = %s AND shares_outstanding IS NOT NULL
                ORDER BY filing_date DESC LIMIT 1
                """,
                (symbol,),
            )
            row = cur.fetchone()
        return int(row[0]) if row and row[0] else None

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
                "data_source": "none",
                "updated_at": now_et,
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
