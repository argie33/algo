"""Regression test: pipeline_health.py's own table registry was missing two exclusions
already known and handled elsewhere in the codebase, live-confirmed via a local orchestrator
run (goal session, 2026-08-23):

- "naaim": NAAIM's free public page permanently transitioned to a subscription model
  2026-08-01, and market_exposure was separately redesigned 2026-08-20 to drop NAAIM entirely
  (see market_exposure_positioning_factor_replaces_naaim_20260820 in memory) - already removed
  from scripts/verify_loaders_health.py's LOADERS dict for the identical reason, but this
  file's own KNOWN_DEPRECATED_TABLES set still reported it VERY_STALE (25 days and climbing
  forever) on every health sweep.
- "algo_untracked_positions": NOT a deprecated loader - actively written by
  algo/infrastructure/alpaca_sync_manager.py, and correctly empty the vast majority of the
  time (no untracked positions = healthy). lambda/api/routes/algo_handlers/market.py already
  excludes it via PIPELINE_REMOVED_TABLES for exactly this reason (see
  test_loader_health_pipeline_removed_tables_excluded.py), but this file had no equivalent
  exclusion, so every sweep reported it MISSING and counted it against coverage_pct.
"""

from algo.monitoring.pipeline_health import HealthStatus, PipelineHealth


def test_naaim_and_untracked_positions_are_in_known_deprecated_tables():
    assert "naaim" in PipelineHealth.KNOWN_DEPRECATED_TABLES
    assert "algo_untracked_positions" in PipelineHealth.KNOWN_DEPRECATED_TABLES


def test_empty_algo_untracked_positions_reports_deprecated_not_missing(monkeypatch):
    """Simulate the row_count==0 branch directly rather than hitting a real DB."""
    import algo.monitoring.pipeline_health as ph

    calls = {"n": 0}

    class _FakeCursor:
        def execute(self, *_a, **_k):
            calls["n"] += 1

        def fetchone(self):
            # First call: pg_class existence check (table exists). Second: exact COUNT(*).
            if calls["n"] == 1:
                return (1,)
            return (0,)

    monitor = PipelineHealth()
    health = monitor.check_table_health(_FakeCursor(), "algo_untracked_positions", None, sla_days=7)

    assert health.status == HealthStatus.DEPRECATED
    # Must NOT use the generic "deprecated loader" wording - this table's loader is active
    # and empty is its normal, healthy state, not a frozen/retired data source.
    assert health.error_message is not None
    assert "deprecated loader" not in health.error_message.lower()
    assert health.is_healthy
