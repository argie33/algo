#!/usr/bin/env python3
"""Regression test: Phase 1's "SESSION 89 FIX" stale-data-reprocessing fallback query (fires
when the required trading day has <50% symbol coverage) must be bounded to a recent date range,
not search the entire history of price_daily unconstrained.

BUG FOUND (goal session, Phase 1 deep-review pass): this fallback query had no date filter at
all - `GROUP BY date ORDER BY coverage DESC LIMIT 1` over the whole table. Since the active
trading universe shrinks over time via delistings, an old date can legitimately out-count
today's partial/in-progress load, so the query could silently pick a date months or years stale.
Traced where the reassigned `max_date` is used afterward: only cosmetic reporting (log lines,
the returned `price_date` field) - Phase 1's own primary staleness halt already used the
correctly-computed date earlier in the function, and Phase 8 independently re-verifies price
freshness with its own bounded query before any entry, so this was not a live path to trading
on stale data. Bounded anyway as defense-in-depth, so a future caller of the reassigned value
(or an operator reading the dashboard's reported price_date) can't be misled by an
arbitrarily-old date.

Static source check (very large function/dependency graph to mock end-to-end for one query
branch - same technique/precedent as test_phase6_portfolio_rotation_writes_audit_log.py).
"""

import re
from pathlib import Path

SOURCE = (Path(__file__).parent.parent.parent / "algo" / "orchestrator" / "phase1_data_freshness.py").read_text()


def _fallback_query_block() -> str:
    match = re.search(
        r"# Fall back to whatever RECENT date has the most data.*?fallback_row = cur\.fetchone\(\)",
        SOURCE,
        re.DOTALL,
    )
    assert match, (
        "expected to find the SESSION 89 stale-reprocessing fallback query - source may have been restructured"
    )
    return match.group(0)


def test_fallback_query_has_a_date_lower_bound():
    block = _fallback_query_block()
    assert "date >= %s" in block, (
        "the fallback query that picks 'whatever date has the most coverage' must be bounded "
        "by a recent date filter - an unbounded GROUP BY over the whole table's history could "
        "pick an arbitrarily old date, since the active symbol universe shrinks over time via "
        "delistings and an old, fully-covered date can out-count today's partial load"
    )


def test_fallback_query_bound_is_relative_to_run_date_not_hardcoded():
    block = _fallback_query_block()
    assert "run_date_obj - td(days=30)" in block or re.search(r"run_date_obj\s*-\s*td\(days=\d+\)", block), (
        "the date bound must be computed relative to run_date_obj (the run being evaluated), "
        "not a fixed calendar date, so this stays correct on every future run"
    )
