"""Regression test for the 2026-08-10 fix (loader-priority half) and its 2026-09-13 correction
(Phase 1 halt/warn half).

2026-08-10: utils/loader_priority.py's PHASE_1_CRITICAL classification for growth_metrics/
quality_metrics/value_metrics/positioning_metrics/stability_metrics contradicted
algo/orchestrator/phase1_data_freshness.py's actual code, which moved all 5 to its warn_tables
dict (Session 221: "website enrichments, not core to signals"). The stale PHASE_1_CRITICAL tag
fed orchestrator.py's _wait_for_critical_loaders_proactive(), which actively waits up to 300s
for PHASE_1_CRITICAL loaders to reach 90%+ completion - live-reproduced growth_metrics/
quality_metrics stuck at status=RUNNING, completion_pct=0.00% for 56+ minutes, burning the full
5-minute proactive wait on every orchestrator run. Fixed by downgrading all 5 to PHASE_1_OPTIONAL.

2026-09-13 (composite-score structural audit): Session 221's underlying premise - "these are
website enrichments, not core to signals" - was itself FALSE. growth_metrics/quality_metrics/
value_metrics/stability_metrics feed stock_scores' Growth/Quality/Value/Risk pillars, and
phase7_signal_generation.py hard-gates real trading candidates on stock_scores.composite_score/
data_completeness (INNER JOIN, no degradation mode). phase1_data_freshness.py's halt_tables/
warn_tables split was corrected to promote those 4 to halt_tables; positioning_metrics correctly
stays in warn_tables (its pillar really was retired 2026-08-27, genuinely display-only).

The PHASE_1_OPTIONAL loader-priority classification is DELIBERATELY left unchanged for all 5 -
that governs whether the orchestrator proactively BLOCKS AND WAITS on the loader (a separate
concern that caused the 2026-08-10 stuck-loader regression), not whether Phase 1 halts on stale
resulting data (now correctly enforced directly via halt_tables instead).
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
HALT_WORTHY_METRICS_TABLES = ["growth_metrics", "quality_metrics", "value_metrics", "stability_metrics"]
WARN_ONLY_METRICS_TABLES = ["positioning_metrics"]


class TestMetricsTablesNotPhase1Critical:
    def test_none_of_the_5_metrics_tables_are_phase1_critical(self) -> None:
        for table in METRICS_TABLES:
            assert get_priority(table) != LoaderPriority.PHASE_1_CRITICAL, (
                f"{table} is PHASE_1_CRITICAL - this would make the orchestrator's proactive-wait "
                "actively block on the loader (the 2026-08-10 stuck-loader regression), which is a "
                "separate concern from Phase 1's own halt_tables check."
            )


def test_metrics_tables_split_matches_phase1_halt_warn_classification() -> None:
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

    for table in HALT_WORTHY_METRICS_TABLES:
        assert f'"{table}"' in halt_block, (
            f"{table} expected in phase1_data_freshness.py's halt_tables - it feeds a live "
            "stock_scores pillar that phase7_signal_generation.py hard-gates real trades on"
        )
        assert f'"{table}"' not in warn_block, f"{table} unexpectedly still in phase1_data_freshness.py's warn_tables"

    for table in WARN_ONLY_METRICS_TABLES:
        assert f'"{table}"' in warn_block, f"{table} expected in phase1_data_freshness.py's warn_tables"
        assert f'"{table}"' not in halt_block, f"{table} unexpectedly in phase1_data_freshness.py's halt_tables"
