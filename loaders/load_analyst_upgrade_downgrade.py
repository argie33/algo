#!/usr/bin/env python3
"""Analyst Upgrade/Downgrade Loader - yfinance Ticker.upgrades_downgrades.

GOVERNANCE: no free official analyst-ratings feed exists (SEC/EDGAR doesn't publish
analyst ratings - it's proprietary, typically a paid feed). This loader restores a real
data feed using the same "unofficial but real, transparently documented" tradeoff already
accepted for put/call ratio (loaders/market_health_fetchers.py::PutCallRatioFetcher) - see
utils/external/yfinance_analyst_ratings.py's docstring for the full rationale.

analyst_upgrade_downgrade had no live writer since Session 275 (load_yfinance_snapshot.py
deletion) - algo/signals/advanced_filters.py::_analyst_score() has been silently scoring
every symbol as "0 net analyst actions" (indistinguishable from genuinely neutral
sentiment) for ~2 months. This loader is a real, additive data source: it does not change
_analyst_score()'s existing logic, which was already correctly built to consume real rows
the moment they exist.

Run:
    python3 loaders/load_analyst_upgrade_downgrade.py [--symbols AAPL,MSFT]
"""

import logging
import sys
from datetime import date

from loaders.runner import run_loader
from loaders.timeout_config import configure_socket_timeout
from utils.external.yfinance_analyst_ratings import fetch_analyst_actions
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)
configure_socket_timeout(30)


class AnalystUpgradeDowngradeLoader(OptimalLoader):
    """Load analyst rating actions (upgrades/downgrades) from yfinance.

    Event-log table (one row per rating action, not a per-symbol snapshot) - most
    symbols legitimately have zero recent actions on any given run, which is not an
    error (matches the existing pattern in load_current_reports_8k.py).
    """

    table_name = "analyst_upgrade_downgrade"
    primary_key = ("symbol", "action_date", "firm")
    watermark_field = "action_date"
    exclude_etfs_from_symbols = True  # ETFs don't get sell-side analyst rating actions
    # A symbol with zero analyst coverage returns an empty list (not a failure - most
    # small/micro-caps genuinely have none). This tolerance is for real fetch failures
    # (yfinance rate-limit/network/parse errors) - yfinance is documented elsewhere in this
    # codebase as more fragile than SEC EDGAR (401-prone "Invalid Crumb" errors under load), so
    # allow more slack than the 2% used for the SEC-sourced loaders.
    max_fail_rate = 15.0

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, object]]:
        """Fetch recent analyst rating actions for this symbol.

        Returns:
            List of new action rows (possibly empty - most symbols have no new activity
            on most runs). Never returns None (OptimalLoader contract).
        """
        rows = fetch_analyst_actions(symbol)
        if not rows:
            return []

        if since is not None:
            # >= not > : a different firm can issue a same-day action after the watermark
            # was already advanced to that date by an earlier run - inclusive re-fetch is
            # idempotent (ON CONFLICT upsert) and matches load_current_reports_8k.py's
            # "on or after" convention.
            rows = [r for r in rows if r["action_date"] >= since]

        return rows


def main() -> int:
    """Entry point for load_analyst_upgrade_downgrade.py."""
    try:
        return run_loader(AnalystUpgradeDowngradeLoader)
    except Exception as e:
        logger.error(f"[ANALYST_UPGRADE_DOWNGRADE FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
