#!/usr/bin/env python3
"""Earnings Calendar Loader - yfinance Ticker.earnings_dates.

GOVERNANCE: no free official forward-looking earnings-date feed exists (SEC/EDGAR filings
never carry future earnings dates - only ANNOUNCED/actual results are official). This
loader uses the same "unofficial but real, transparently documented" tradeoff already
accepted for analyst_upgrade_downgrade/analyst_sentiment_analysis/analyst_earnings_estimates
- see utils/external/yfinance_analyst_ratings.py's docstring for the full rationale.

earnings_calendar had no live writer since 2026-07-19 (load_yfinance_derived_metrics.py
deleted as part of Session 295's "8 orphaned loaders" cleanup, believed already superseded
by the SEC loaders - it wasn't, for this table: earnings_calendar_sec covers SEC *filing*
dates for 10-K/10-Q, a different concept from earnings *announcement* dates with EPS
estimates/actuals). Despite having no active loader, this table is still:
- marked PHASE_1_CRITICAL in utils/loader_priority.py
- treated as halt-critical in algo/orchestrator/phase1_data_freshness.py
- read live by algo/risk/earnings_blackout.py on every entry to gate trades around
  earnings announcements

The Phase 1 freshness check compares against earnings_date (a forward-looking calendar
column, populated years ahead for scheduled dates) rather than a load timestamp, so it
could never detect this staleness - confirmed live 2026-08-04: created_at frozen at
2026-07-23 (12 days stale and growing) while earnings_date still ranged out to
2026-12-08, silently passing every freshness check. Same "believed superseded" mistake
class already fixed for analyst_upgrade_downgrade/analyst_sentiment_analysis/
analyst_earnings_estimates - this loader closes the last one of that batch.

Run:
    python3 loaders/load_earnings_calendar.py [--symbols AAPL,MSFT]
"""

import logging
import sys
from datetime import date, datetime

from loaders.runner import run_loader
from loaders.timeout_config import configure_socket_timeout
from utils.external.yfinance_analyst_ratings import fetch_earnings_calendar
from utils.infrastructure.timezone import EASTERN_TZ
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)
configure_socket_timeout(30)


class EarningsCalendarLoader(OptimalLoader):
    """Load recent-past and upcoming earnings dates per symbol from yfinance.

    Event-log table (one row per earnings date, not a per-symbol snapshot) - most
    symbols have real earnings-date coverage; OTC/delisted/pre-IPO symbols with none are
    marked data_unavailable, not an error.
    """

    table_name = "earnings_calendar"
    primary_key = ("symbol", "earnings_date")
    watermark_field = "earnings_date"
    exclude_etfs_from_symbols = True  # ETFs don't report single-company earnings
    # Mirrors analyst_upgrade_downgrade/analyst_earnings_estimates: no coverage is a real,
    # common, non-error outcome for OTC/delisted/rights-offering/micro-cap symbols.
    max_fail_rate = 35.0

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, object]]:
        """Fetch this symbol's current earnings-date window from yfinance.

        Deliberately ignores `since`: yfinance's earnings_dates always returns the same
        rolling ~12-past/1-future window regardless of what we already have, and a row
        that was estimate-only (actual_eps NULL) before an earnings date passes needs to
        be re-fetched afterward to pick up the real actual_eps/surprise_pct - a
        since-based skip would freeze that row at its pre-earnings estimate forever.
        ON CONFLICT (symbol, earnings_date) upsert makes re-sending the whole window
        idempotent.
        """
        try:
            rows = fetch_earnings_calendar(symbol)
        except RuntimeError as e:
            return [self._unavailable_record(symbol, f"fetch_error:{type(e).__name__}")]

        if rows is None:
            return [self._unavailable_record(symbol, "no_earnings_coverage")]

        # Explicit updated_at=now on every row (not left to DB defaults, which only fire on
        # INSERT): this table's freshness monitors (monitor_data_staleness.py,
        # phase1_data_freshness.py) key off MAX(updated_at), not the forward-looking
        # earnings_date column - see this module's docstring for why that switch mattered.
        # An UPDATE branch that never touches updated_at would silently reintroduce the same
        # blind spot this loader was restored to fix.
        now = datetime.now(EASTERN_TZ)
        return [
            {
                "symbol": r["symbol"],
                "earnings_date": r["earnings_date"],
                "announce_time": None,
                "eps_estimate": r["eps_estimate"],
                "actual_eps": r["actual_eps"],
                "revenue_estimate": None,
                "actual_revenue": None,
                "fiscal_period": None,
                "company_name": None,
                "status": None,
                "surprise_pct": r["surprise_pct"],
                "fiscal_quarter": None,
                "fiscal_year": None,
                "data_unavailable": False,
                "reason": None,
                "updated_at": now,
            }
            for r in rows
        ]

    def _unavailable_record(self, symbol: str, reason: str) -> dict[str, object]:
        now = datetime.now(EASTERN_TZ)
        return {
            "symbol": symbol,
            "earnings_date": now.date(),
            "announce_time": None,
            "eps_estimate": None,
            "actual_eps": None,
            "revenue_estimate": None,
            "actual_revenue": None,
            "fiscal_period": None,
            "company_name": None,
            "status": None,
            "surprise_pct": None,
            "fiscal_quarter": None,
            "fiscal_year": None,
            "data_unavailable": True,
            "reason": reason,
            "updated_at": now,
        }


def main() -> int:
    """Entry point for load_earnings_calendar.py."""
    try:
        return run_loader(EarningsCalendarLoader)
    except Exception as e:
        logger.error(f"[EARNINGS_CALENDAR FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
