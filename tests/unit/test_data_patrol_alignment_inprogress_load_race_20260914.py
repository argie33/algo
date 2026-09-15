"""Regression test for AlignmentChecker.check_cross_table_alignment's in-progress-load
race (algo/monitoring/data_patrol/checks/alignment.py) - same bug shape as coverage.py's
check_loader_coverage (see test_data_patrol_coverage_inprogress_load_race_20260914.py),
found the same session by auditing every other DataPatrol checker for the identical
"bare MAX(date)" pattern once the coverage.py instance was live-confirmed.

check_cross_table_alignment compares technical_data_daily/trend_template_data's own
bare-MAX(date) symbol count against a `baseline` derived from price_daily's own bare-
MAX(date) count. If either table's MAX(date) has just flipped to a brand-new trading day
with only a handful of rows landed so far - while the OTHER table is still sitting on a
complete prior day - the ratio crashes toward zero (or baseline itself is tiny) and fires
a false ERROR (technical_data_daily) or WARN (trend_template_data) against a load that
simply hasn't finished yet, not a genuine cross-table drift.

Locks in that both the baseline query and the per-table date clauses require a candidate
date to already clear a minimum symbol floor before trusting it.
"""

import inspect

from algo.monitoring.data_patrol.checks.alignment import AlignmentChecker


def test_cross_table_alignment_guards_against_in_progress_load_race() -> None:
    source = inspect.getsource(AlignmentChecker.check_cross_table_alignment)
    assert "_race_resistant_date_where" in source, (
        "check_cross_table_alignment's per-table date clauses must not compare against a "
        "bare MAX(date) - a brand-new trading day's first few rows on either table would "
        "crash the ratio to near zero before that table's load finishes."
    )
    assert "COALESCE" in source, (
        "the baseline price_daily query must also fall back to the bare MAX(date) only "
        "when no recent date clears the in-progress-load floor - see the fix's own "
        "docstring."
    )
