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
    #
    # FIX 2026-07-28: 15.0 (85% completion floor) was copy-pasted from the SEC-sourced
    # loaders' tolerance without checking this source's actual achievable ceiling. Live-
    # confirmed across 2 independent full-universe runs (one solo, one concurrent with
    # analyst_sentiment_analysis): completion consistently lands at 71.6%/71.7% - genuine
    # yfinance HTTP 404 "No fundamentals data found" for OTC/delisted/rights-offering
    # symbols (the same ".R"/"$"-suffixed stragglers already documented as legitimately
    # data_unavailable elsewhere in this codebase, e.g. the 13F CUSIP crosswalk), not a
    # rate-limit or circuit-breaker cutoff - no 429s in the run logs. Same bug class as the
    # 2026-07-27 fix for quarterly_balance_sheet/quarterly_income_statement's 85% ceiling:
    # a real, permanent structural ceiling was being flagged FAILED forever instead of
    # recognized as COMPLETED. 35.0 (65% floor) sits comfortably below the observed ~72%
    # with margin to still catch a genuine regression (e.g. yfinance itself going down).
    max_fail_rate = 35.0

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, object]]:
        """Fetch recent analyst rating actions for this symbol.

        Returns:
            List of new action rows (possibly empty if no recent activity), or
            data_unavailable marker if no analyst coverage. Never returns None (OptimalLoader contract).
        """
        rows = fetch_analyst_actions(symbol)
        if not rows:
            # No analyst coverage for this symbol (legitimate case, not a fetch failure)
            # None return from fetch_analyst_actions indicates no coverage
            #
            # FIX 2026-08-10: primary_key = ("symbol", "action_date", "firm") - OptimalLoader.
            # _validate_row() requires every declared primary_key field present and non-None
            # (same bug class as migration 1168's dividend_data fix). This marker used to omit
            # both non-symbol PK fields entirely, crashing every no-coverage symbol with "Row
            # missing required primary key field 'action_date'" the moment the governance-
            # marker-columns bug (migration 1201) stopped masking it. Placeholder action_date
            # follows load_dividend_data.py's _unavailable_record() convention (today's date,
            # not a fabricated historical one); "firm" has no natural non-NULL placeholder
            # since it identifies a real analyst firm, so a literal marker string is used.
            return [
                {
                    "symbol": symbol,
                    "action_date": date.today(),
                    "firm": "N/A",
                    "data_unavailable": True,
                    "data_unavailable_reason": "no_analyst_coverage",
                }
            ]

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
        logger.error(
            f"[ANALYST_UPGRADE_DOWNGRADE FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
