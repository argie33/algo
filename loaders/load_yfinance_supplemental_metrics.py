#!/usr/bin/env python3
"""Yfinance Supplemental Metrics Loader - held_percent_insiders via yfinance major_holders.

GOVERNANCE: this field (% of shares held by insiders) has no SEC-XBRL source - it isn't a
standard us-gaap/dei concept, Yahoo computes it from proprietary share-registry data. Uses
yf.Ticker(symbol).major_holders, a real non-.info DataFrame *property* endpoint (same
"unofficial but real, transparently documented" tradeoff already accepted for analyst
ratings/estimates - see utils/external/yfinance_analyst_ratings.py's docstring). Deliberately
a property access, not `.get_major_holders()`: YFinanceTimeoutWrapper.__getattr__ only wraps
attribute *lookup* in its per-call timeout, so calling a method it returns (e.g.
`wrapper.get_major_holders()`) executes the actual network fetch outside the timeout
enforcement entirely - the same unbounded-hang failure mode this wrapper was built to prevent
(see this module's own docstring: a stuck yfinance call once hung a loader for 5+ hours).
`.major_holders` is a plain DataFrame property (live-verified 2026-09-14, same shape as
`.get_major_holders()`'s default), so `wrapper.major_holders` gets real timeout coverage like
every other property-based fetch in this codebase (upgrades_downgrades, recommendations_summary,
earnings_estimate). Deliberately NOT using yfinance's
`.info`/quoteSummary endpoint - that whole API surface was removed from this codebase
2026-07-21 (steering/DATA_LOADERS.md) after real 401/"Invalid Crumb" production incidents and
risk of tripping the shared cross-ECS-task yfinance circuit breaker the OHLCV fallback path
depends on.

Snapshot-per-symbol table (single row per symbol, refreshed in place - like
analyst_sentiment_analysis's daily row but with no history retained, since ownership
percentage moves slowly and there's no research use case for a daily time series of it yet).

Run:
    python3 loaders/load_yfinance_supplemental_metrics.py [--symbols AAPL,MSFT]
"""

import logging
import sys
from datetime import date, datetime

from loaders.runner import run_loader
from loaders.timeout_config import configure_socket_timeout
from utils.external.yfinance_timeout_wrapper import YFinanceTimeoutWrapper
from utils.infrastructure.timezone import EASTERN_TZ
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)
configure_socket_timeout(30)


def _fetch_held_percent_insiders(symbol: str) -> tuple[float | None, str | None]:
    """Fetch insider-ownership % via yfinance's major_holders DataFrame (non-.info endpoint).

    Returns (percent_as_0_to_100, unavailable_reason). yfinance reports insidersPercentHeld
    as a 0-1 fraction; scaled to 0-100 to match this codebase's other percentage columns
    (e.g. positioning_metrics.institutional_ownership_pct).
    """
    try:
        wrapper = YFinanceTimeoutWrapper(symbol, timeout_sec=15.0)
        major_holders = wrapper.major_holders
    except (RuntimeError, TimeoutError) as e:
        logger.debug(f"[{symbol}] yfinance major_holders fetch failed: {e}")
        return None, "yfinance_fetch_failed"
    except Exception as e:
        logger.debug(f"[{symbol}] yfinance major_holders fetch error: {e}")
        return None, "yfinance_fetch_failed"

    if major_holders is None or major_holders.empty or "insidersPercentHeld" not in major_holders.index:
        return None, "no_insider_ownership_data"

    try:
        raw = major_holders.loc["insidersPercentHeld"].iloc[0]
    except (KeyError, IndexError):
        return None, "no_insider_ownership_data"

    if raw is None:
        return None, "no_insider_ownership_data"
    try:
        pct = float(raw) * 100.0
    except (TypeError, ValueError):
        return None, "no_insider_ownership_data"

    if pct != pct or pct < 0 or pct > 100:  # NaN or out-of-range
        return None, "implausible_value"

    return pct, None


class YfinanceSupplementalMetricsLoader(OptimalLoader):
    """Load held_percent_insiders (and future non-.info yfinance-only supplemental fields)."""

    table_name = "yfinance_supplemental_metrics"
    primary_key = ("symbol",)
    watermark_field = "updated_at"
    exclude_etfs_from_symbols = True  # ETFs have no "insiders" in the equity-ownership sense
    # Ownership % moves slowly and this is a brand-new, low-priority supplemental field -
    # a generous floor avoids false-alarming on the same structural micro-cap/OTC coverage
    # gaps already documented for analyst_sentiment_analysis (max_fail_rate=25.0 there).
    max_fail_rate = 40.0

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, object]]:
        """Fetch this symbol's current held_percent_insiders snapshot.

        Refreshes at most once per day (matches analyst_sentiment_analysis's cadence) - not
        worth re-fetching intraday for a figure that moves on the timescale of insider
        Form 4 filings, not minutes.
        """
        today = datetime.now(EASTERN_TZ).date()
        if since is not None and since >= today:
            return []  # already have today's snapshot

        held_percent_insiders, reason = _fetch_held_percent_insiders(symbol)

        return [
            {
                "symbol": symbol,
                "held_percent_insiders": held_percent_insiders,
                "held_percent_insiders_unavailable_reason": reason,
                "data_source": "yfinance",
                "data_unavailable": held_percent_insiders is None,
                "reason": reason,
                "updated_at": datetime.now(EASTERN_TZ),
            }
        ]


def main() -> int:
    return run_loader(YfinanceSupplementalMetricsLoader)


if __name__ == "__main__":
    sys.exit(main())
