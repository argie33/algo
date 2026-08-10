"""Regression test for the 2026-08-10 fix: utils/loader_priority.py's PHASE_1_CRITICAL
classification for growth_metrics/quality_metrics/value_metrics/positioning_metrics/
stability_metrics contradicted algo/orchestrator/phase1_data_freshness.py's actual code,
which moved all 5 to its warn_tables dict (Session 221: "website enrichments, not core to
signals" - stale means logged, trading continues, not halted).

The stale PHASE_1_CRITICAL tag fed orchestrator.py's _wait_for_critical_loaders_proactive(),
which actively waits up to 300s for PHASE_1_CRITICAL loaders to reach 90%+ completion -
live-reproduced growth_metrics/quality_metrics stuck at status=RUNNING, completion_pct=0.00%
for 56+ minutes, which would have burned the full 5-minute proactive wait on every
orchestrator run for tables Phase 1 doesn't actually require.

Fixed by downgrading all 5 to PHASE_1_OPTIONAL, matching phase1_data_freshness.py's actual,
documented, deliberate behavior.
"""

from pathlib import Path

from utils.loader_priority import LoaderPriority, get_priority

REPO_ROOT = Path(__file__).resolve().parents[2]
METRICS_TABLES = [
    "growth_metrics",
    "quality_metrics",
    "value_metrics",
    "positioning_metrics",
    "stability_metrics",
]


class TestMetricsTablesNotPhase1Critical:
    def test_none_of_the_5_metrics_tables_are_phase1_critical(self) -> None:
        for table in METRICS_TABLES:
            assert get_priority(table) != LoaderPriority.PHASE_1_CRITICAL, (
                f"{table} is PHASE_1_CRITICAL, contradicting phase1_data_freshness.py's "
                "warn_tables treatment - this would make the proactive-wait actively block "
                "the orchestrator on a table Phase 1 itself only warns about."
            )


def test_metrics_tables_are_actually_in_phase1_warn_tables_not_halt_tables() -> None:
    """Sanity check tying this test back to the real Phase 1 behavior it claims to match,
    so it can't silently drift if phase1_data_freshness.py's own dicts change."""
    source = (REPO_ROOT / "algo" / "orchestrator" / "phase1_data_freshness.py").read_text(encoding="utf-8")
    # Both dicts are local variables inside a method, not module-level - find via source scan.
    assert "warn_tables = {" in source
    assert "halt_tables = {" in source
    warn_block_start = source.index("warn_tables = {")
    warn_block_end = source.index("}", warn_block_start)
    warn_block = source[warn_block_start:warn_block_end]
    halt_block_start = source.index("halt_tables = {")
    halt_block_end = source.index("}", halt_block_start)
    halt_block = source[halt_block_start:halt_block_end]

    for table in METRICS_TABLES:
        assert f'"{table}"' in warn_block, f"{table} expected in phase1_data_freshness.py's warn_tables"
        assert f'"{table}"' not in halt_block, f"{table} unexpectedly in phase1_data_freshness.py's halt_tables"
