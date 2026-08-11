"""Regression test: PIPELINE_REMOVED_TABLES (lambda/api/routes/algo_handlers/market.py,
the actual source for the dashboard's DATA FRESHNESS panel) must never drift out of sync
with algo/monitoring/pipeline_health.py's KNOWN_DEPRECATED_TABLES.

Live-confirmed 2026-08-11 (via /goal): the dashboard reported "44/49 fresh, 5 stale" and
2 of those 5 - sec_cash_flow_metrics and algo_performance_metrics - are tables with no
writer at all, already documented as dead and added to KNOWN_DEPRECATED_TABLES (on
2026-07-27 and 2026-08-10 respectively). Both were hand-duplicated into
PIPELINE_REMOVED_TABLES as a separate literal instead of sharing the one list, so the
addition to KNOWN_DEPRECATED_TABLES never propagated - the dashboard kept reporting both
as false STALE for weeks after they were "fixed" in the other module.

market.py now unions PipelineHealth.KNOWN_DEPRECATED_TABLES into PIPELINE_REMOVED_TABLES
instead of copying entries, so this can't recur for any *future* addition either.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def test_pipeline_removed_tables_is_a_superset_of_known_deprecated_tables():
    from routes.algo_handlers.market import PIPELINE_REMOVED_TABLES

    from algo.monitoring.pipeline_health import PipelineHealth

    missing = PipelineHealth.KNOWN_DEPRECATED_TABLES - PIPELINE_REMOVED_TABLES
    assert not missing, (
        f"KNOWN_DEPRECATED_TABLES entries missing from PIPELINE_REMOVED_TABLES: {missing} "
        "- the dashboard's freshness panel will falsely report these as STALE."
    )


def test_the_two_live_confirmed_drifted_tables_are_excluded():
    from routes.algo_handlers.market import PIPELINE_REMOVED_TABLES

    assert "sec_cash_flow_metrics" in PIPELINE_REMOVED_TABLES
    assert "algo_performance_metrics" in PIPELINE_REMOVED_TABLES
