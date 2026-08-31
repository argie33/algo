"""Regression test: the Phase 9 portfolio-snapshot health check
(lambda/api/routes/algo_handlers/market.py's `_get_data_status`) used
`MAX(snapshot_date)` and `MAX(total_portfolio_value)` as independent aggregates over the
whole `algo_portfolio_snapshots` table with no pairing to the same row. After any drawdown
from a prior peak (routine, not an edge case), this silently returned the all-time HIGHEST
portfolio value mislabeled as the "latest" one alongside the real latest date - an operator
reading this health endpoint during/after a real drawdown would see an inflated current
portfolio value and could underestimate real risk exposure.

Fixed to select snapshot_date and total_portfolio_value from the SAME row (the true latest
one via ORDER BY ... LIMIT 1), matching the correct pattern already used elsewhere in this
codebase (e.g. position_sizer.py's get_portfolio_value snapshot fallback), and bounded by
`snapshot_date <= CURRENT_DATE` - the same "stray future-dated snapshot" bug class fixed
2026-08-09 elsewhere (see test_no_unbounded_portfolio_snapshot_queries.py).

This is a static-pattern regression test, not an execution test, matching the established
convention for this exact bug class in this codebase (the unit suite's global DB mock makes
a live-query execution test for one deeply-nested query impractical - see conftest.py).
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MARKET_PY = REPO_ROOT / "lambda" / "api" / "routes" / "algo_handlers" / "market.py"


def _phase9_query_block() -> str:
    text = MARKET_PY.read_text(encoding="utf-8")
    marker = "# Phase 9: Portfolio Snapshot Health"
    start = text.index(marker)
    # The block is short - grab a generous window past the marker.
    return text[start : start + 2000]


def test_phase9_health_does_not_use_independent_max_aggregates():
    """The exact bug: two unrelated MAX(...) calls in one SELECT with no row pairing."""
    block = _phase9_query_block()
    assert not re.search(r"MAX\(snapshot_date\).*\n.*MAX\(total_portfolio_value\)", block), (
        "Phase 9 portfolio snapshot health check regressed to independent MAX(snapshot_date)/"
        "MAX(total_portfolio_value) aggregates - this pairs an unrelated historical peak value "
        "with the latest date. Use an ORDER BY snapshot_date DESC LIMIT 1 subquery instead so "
        "date and value always come from the same row."
    )


def test_phase9_health_pairs_date_and_value_from_same_row():
    """The fix: date and value must come from a single ORDER BY ... LIMIT 1 latest row."""
    block = _phase9_query_block()
    assert re.search(r"ORDER BY snapshot_date DESC\s*\n\s*LIMIT 1", block), (
        "Expected the Phase 9 health check's latest-snapshot lookup to use "
        "ORDER BY snapshot_date DESC LIMIT 1 to pair date and value from the same row."
    )


def test_phase9_health_bounds_latest_snapshot_by_current_date():
    """Same 'stray future-dated snapshot' bug class fixed 2026-08-09 elsewhere - this lookup
    must not be exempt just because it's a health-check endpoint, not a risk-decision path."""
    block = _phase9_query_block()
    assert re.search(r"snapshot_date\s*<=\s*CURRENT_DATE", block), (
        "Phase 9 health check's latest-snapshot lookup is missing the snapshot_date <= "
        "CURRENT_DATE bound - a stray future-dated row (e.g. a leftover local --date "
        "simulation snapshot) could outrank the real current one."
    )
