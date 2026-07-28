#!/usr/bin/env python3
"""Analyst Sentiment Analysis Loader - yfinance recommendations_summary + price targets.

GOVERNANCE: no free official analyst-ratings feed exists (SEC/EDGAR doesn't publish
analyst recommendations - it's proprietary, typically a paid feed). This loader restores
a real data feed using the same "unofficial but real, transparently documented" tradeoff
already accepted for put/call ratio and analyst_upgrade_downgrade - see
utils/external/yfinance_analyst_ratings.py's docstring for the full rationale.

analyst_sentiment_analysis had no live writer since Session 275 (load_yfinance_snapshot.py
deletion) - lambda/api/routes/sentiment.py's /api/sentiment/analyst/* endpoints have been
correctly fail-fasting with "data is N days stale" for ~2 months rather than serving stale
data (the right behavior for a missing source, but still a missing source).

Run:
    python3 loaders/load_analyst_sentiment_analysis.py [--symbols AAPL,MSFT]
"""

import logging
import sys
from datetime import date, datetime

from loaders.runner import run_loader
from loaders.timeout_config import configure_socket_timeout
from utils.external.yfinance_analyst_ratings import fetch_analyst_sentiment
from utils.infrastructure.timezone import EASTERN_TZ
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)
configure_socket_timeout(30)


class AnalystSentimentAnalysisLoader(OptimalLoader):
    """Load a daily analyst-recommendation summary per symbol from yfinance.

    Snapshot-per-day table (one row per symbol per day, not an event log) - most symbols
    have real analyst coverage; small/micro-caps with none are skipped (empty result), not
    an error.
    """

    table_name = "analyst_sentiment_analysis"
    primary_key = ("symbol", "date")
    watermark_field = "date"
    exclude_etfs_from_symbols = True  # ETFs don't get sell-side analyst coverage
    # Same reasoning as load_analyst_upgrade_downgrade.py: no coverage returns an empty list
    # (not a failure). This tolerance is for real yfinance fetch failures.
    max_fail_rate = 15.0

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, object]]:
        """Fetch today's analyst sentiment summary for this symbol.

        Returns:
            List with one row (today's summary), or empty if no analyst coverage or
            already fetched today (watermark). Never returns None (OptimalLoader contract).
        """
        today = datetime.now(EASTERN_TZ).date()
        if since is not None and since >= today:
            return []  # already have today's snapshot

        summary = fetch_analyst_sentiment(symbol)
        if summary is None:
            return []

        summary["date"] = today
        return [summary]


def main() -> int:
    """Entry point for load_analyst_sentiment_analysis.py."""
    try:
        return run_loader(AnalystSentimentAnalysisLoader)
    except Exception as e:
        logger.error(
            f"[ANALYST_SENTIMENT_ANALYSIS FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
