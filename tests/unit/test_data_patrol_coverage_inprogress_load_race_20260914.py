"""Regression test for CoverageChecker.check_loader_coverage's in-progress-load race
(algo/monitoring/data_patrol/checks/coverage.py) - live-reproduced 2026-09-14: a real
DataPatrol run (patrol_run_id 7c0d02266a824df3ac1fba984c8f5355) flagged price_daily
coverage as 0.2% (10/5145) ERROR because a brand-new trading day's very first few rows
had already landed (a real-time write, or a queued "signals" pipeline run just starting
its "prices" step), flipping MAX(date) to that still-loading day before it had a chance
to fill in. Since Phase 1 (phase1_data_freshness.py) gates live trading on the MOST
RECENT DataPatrol run regardless of what produced it, this false ERROR could halt
trading on a load that finishes normally minutes later.

The real fix lives in the SQL itself (each table's reference date must already clear
in_progress_load_floor symbols, falling back to plain MAX(date) only if no recent date
does) - this test locks in that shape so it can't be silently reverted back to a bare
MAX(date) comparison.
"""

import inspect

from algo.monitoring.data_patrol.checks.coverage import CoverageChecker


def test_loader_coverage_query_guards_against_in_progress_load_race() -> None:
    source = inspect.getsource(CoverageChecker.check_loader_coverage)
    assert "in_progress_load_floor" in source, (
        "check_loader_coverage must not compare against a bare MAX(date) - a brand-new "
        "trading day's first few rows would flip MAX(date) before the load finishes, "
        "producing a false coverage ERROR (live-reproduced 2026-09-14, patrol_run_id "
        "7c0d02266a824df3ac1fba984c8f5355: price_daily 0.2%% (10/5145))."
    )
    assert "COALESCE" in source, (
        "the reference-date selection must fall back to the bare MAX(date) only when no "
        "recent date clears the in-progress-load floor - see the fix's own comment."
    )
