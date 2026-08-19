#!/usr/bin/env python3
"""Analyst Earnings Estimates Loader - yfinance Ticker.earnings_estimate (forward EPS).

GOVERNANCE: no free official forward-EPS feed exists (SEC/EDGAR filings never carry
forward-looking estimates - by definition, they're third-party analyst consensus, not an
audited historical fact). This loader uses the same "unofficial but real, transparently
documented" tradeoff already accepted for analyst_upgrade_downgrade/analyst_sentiment_analysis
- see utils/external/yfinance_analyst_ratings.py's docstring for the full rationale.

value_metrics.forward_pe was previously hardcoded None every run (correctly, since no
forward-EPS source existed) - this loader gives it a real one.
FEEDS: load_value_quality_growth_metrics.py joins this table by symbol to compute
forward_pe = current_price / forward_eps.

Run:
    python3 loaders/load_analyst_earnings_estimates.py [--symbols AAPL,MSFT]
"""

import logging
import sys
from datetime import date, datetime

from loaders.runner import run_loader
from loaders.timeout_config import configure_socket_timeout
from utils.db.context import DatabaseContext
from utils.external.yfinance_analyst_ratings import fetch_forward_eps
from utils.infrastructure.timezone import EASTERN_TZ
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)
configure_socket_timeout(30)


class AnalystEarningsEstimatesLoader(OptimalLoader):
    """Load a daily consensus forward-EPS snapshot per symbol from yfinance.

    Snapshot-per-day table (one row per symbol per day, not an event log) - most symbols
    have real analyst coverage; small/micro-caps with none are marked data_unavailable,
    not an error.
    """

    table_name = "analyst_earnings_estimates"
    primary_key = ("symbol", "date")
    watermark_field = "date"
    exclude_etfs_from_symbols = True  # ETFs don't get sell-side analyst EPS estimates
    # SESSION 91 FIX (RC-3): Increased from 35 (65% floor) to 25 (75% floor) to catch
    # real failures while acknowledging live-confirmed ~72% ceiling for OTC/micro-caps.
    # No coverage = legitimate data_unavailable (not an error), but <72% completion on a
    # run suggests network issues, yfinance circuit breaker, or rate-limiting that should
    # halt. 75% floor catches these while tolerating the structural ceiling.
    # Why: forward_eps feeds value_metrics.forward_pe, which affects signal generation.
    # Incomplete/degraded forward_pe affects all downstream scoring quality.
    max_fail_rate = 25.0

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, object]]:
        """Fetch today's forward-EPS estimate for this symbol.

        Returns:
            List with one row (today's snapshot), or data_unavailable marker if no
            analyst coverage. Never returns None (OptimalLoader contract).
        """
        today = datetime.now(EASTERN_TZ).date()
        if since is not None and since >= today:
            return []  # already have today's snapshot

        forward_eps = fetch_forward_eps(symbol)
        if forward_eps is None:
            # FIX 2026-08-19 (goal: "no SEC data" audit, parity with the sibling analyst
            # loaders' 2026-08-18 fix): this loader never got the "skip the marker write for
            # a symbol with prior real coverage" guard its siblings
            # (load_analyst_upgrade_downgrade.py, load_analyst_sentiment_analysis.py)
            # already have - a transient today-only yfinance hiccup would write a fresh
            # data_unavailable marker dated today(), which (this being a snapshot-per-day
            # table keyed on (symbol, date)) becomes the "latest row per symbol" the moment
            # it's written, masking real historical forward-EPS coverage for that one day.
            # Unlike the sibling loaders this table mostly self-heals on the next successful
            # day (the marker's date isn't artificially inflated the way the event-log
            # table's was), but there's no reason to manufacture the false negative even for
            # a single day when a real answer is already on record. Live-confirmed low
            # current impact (9 symbols with real history currently masked this way) but same
            # bug class - fixed for consistency and to stop it from growing.
            if self._has_prior_real_coverage(symbol):
                return []
            return [
                {
                    "symbol": symbol,
                    "date": today,
                    "forward_eps": None,
                    "data_unavailable": True,
                    "reason": "no_analyst_estimates",
                }
            ]

        return [
            {
                "symbol": symbol,
                "date": today,
                "forward_eps": forward_eps,
                "data_unavailable": False,
                "reason": None,
            }
        ]

    @staticmethod
    def _has_prior_real_coverage(symbol: str) -> bool:
        """True if this symbol already has at least one real (non-marker) row on record."""
        with DatabaseContext("read") as cur:
            cur.execute(
                "SELECT 1 FROM analyst_earnings_estimates WHERE symbol = %s AND data_unavailable = false LIMIT 1",
                (symbol,),
            )
            return cur.fetchone() is not None


def main() -> int:
    """Entry point for load_analyst_earnings_estimates.py."""
    try:
        return run_loader(AnalystEarningsEstimatesLoader)
    except Exception as e:
        logger.error(
            f"[ANALYST_EARNINGS_ESTIMATES FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
