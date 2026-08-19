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
from utils.db.context import DatabaseContext
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
    # recognized as COMPLETED. 35.0 (65% floor) was too permissive.
    # SESSION 91 FIX (RC-3): Increased to 25.0 (75% floor) to catch real API failures
    # while respecting ~72% structural ceiling. 65% allows too much data degradation.
    max_fail_rate = 25.0

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, object]]:
        """Fetch recent analyst rating actions for this symbol.

        Returns:
            List of new action rows (possibly empty if no recent activity), or
            data_unavailable marker if no analyst coverage. Never returns None (OptimalLoader contract).
        """
        try:
            rows = fetch_analyst_actions(symbol)
        except RuntimeError as e:
            logger.warning(f"[{symbol}] yfinance fetch failed: {e} - treating as data unavailable")
            rows = None

        if not rows:
            # FIX 2026-08-18 (goal session, "which factor inputs are missing the most" audit):
            # an empty fetch_analyst_actions() result used to ALWAYS write a fresh
            # "no_analyst_coverage" marker (action_date=today), even for symbols with a long
            # real history already in this table. Since this is an append-only event log, a
            # marker's action_date=today() is virtually guaranteed to be >= every real
            # historical action_date, so it permanently wins any "latest row per symbol" read
            # (e.g. scripts/audit_unavailable_reasons.py) - live-confirmed 3,507 of 4,678
            # "no_analyst_coverage" symbols already had real rows, including NVDA (308 real
            # rows, continuously covered) intermittently showing an empty yfinance response on
            # specific run days (2026-08-12/13/16) - almost certainly transient upstream
            # flakiness, not NVDA losing analyst coverage. A symbol that has EVER had a real
            # row is overwhelmingly more likely mid-transient-hiccup than newly uncovered, so
            # skip the marker write for it (this run simply found nothing new - already a
            # normal, expected outcome per this loader's own docstring) and only mark
            # data_unavailable for symbols that have NEVER had real coverage.
            if self._has_prior_real_coverage(symbol):
                return []

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

        # FIX 2026-08-19 (goal: "no SEC data"/loader audit, follow-up to the 2026-08-18 fix
        # above): that fix stops WRITING new markers once a symbol has real coverage, but
        # never retracted markers already written before it landed - live-confirmed NVDA
        # (308 real rows, continuously covered), MSFT, TSM, GOOGL and other mega-caps still
        # carry an unretracted marker dated 2026-08-16 (firm='N/A', action_date=today() at
        # write time), which is a DIFFERENT primary-key row (symbol, action_date, firm) from
        # any real action - ON CONFLICT upsert never touches it. Since a marker's
        # action_date is always "today" at write time, it is virtually guaranteed to sort
        # after real historical actions forever, permanently shadowing genuine, current
        # analyst coverage in any "latest row per symbol" read (the coverage dashboard,
        # scripts/audit_unavailable_reasons.py) even though this exact run just proved
        # coverage is real and current. Retract every marker for this symbol whenever the
        # raw fetch (before the `since` incremental-window filter below, which could
        # legitimately trim every row away for a symbol with only old history and nothing
        # new since the last watermark - that must not block the retraction) returns real
        # data - the strongest possible evidence a marker was wrong is a real row landing
        # for that same symbol.
        with DatabaseContext("write") as cur:
            cur.execute(
                "DELETE FROM analyst_upgrade_downgrade WHERE symbol = %s AND data_unavailable = true",
                (symbol,),
            )

        if since is not None:
            # >= not > : a different firm can issue a same-day action after the watermark
            # was already advanced to that date by an earlier run - inclusive re-fetch is
            # idempotent (ON CONFLICT upsert) and matches load_current_reports_8k.py's
            # "on or after" convention.
            rows = [r for r in rows if r["action_date"] >= since]

        return rows

    @staticmethod
    def _has_prior_real_coverage(symbol: str) -> bool:
        """True if this symbol already has at least one real (non-marker) row on record."""
        with DatabaseContext("read") as cur:
            cur.execute(
                "SELECT 1 FROM analyst_upgrade_downgrade WHERE symbol = %s AND data_unavailable = false LIMIT 1",
                (symbol,),
            )
            return cur.fetchone() is not None


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
