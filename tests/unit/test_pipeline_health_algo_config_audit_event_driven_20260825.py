"""Regression test: pipeline_health.py flagged algo_config_audit STALE (8 days old vs. a
7-day SLA) even though it's correctly, actively written - it just only writes on a real
config VALUE change (AlgoConfig.set() deliberately skips no-op "same value" writes, see
that method's own "Skip no-op writes" comment). Live-confirmed 2026-08-25: the two most
recent algo_config.updated_at bumps in the stale window (execution_mode's repeated
"paper -> paper" no-op re-writes from run_local_orchestrator.py's per-run force-paper guard,
and exit_limit_slippage_buffer_bps seeded once by migration 1218) were both legitimately
unaudited, not a real audit-trail bypass. A flat calendar-day SLA has no correct value for a
table with no guaranteed write cadence - added to KNOWN_DEPRECATED_TABLES (same pattern as
algo_untracked_positions) so it stops permanently capping coverage_pct below 100% for a
non-issue.
"""

from datetime import date
from typing import Any

from algo.monitoring.pipeline_health import HealthStatus, PipelineHealth


def test_algo_config_audit_is_in_known_deprecated_tables() -> None:
    assert "algo_config_audit" in PipelineHealth.KNOWN_DEPRECATED_TABLES


def test_old_algo_config_audit_reports_deprecated_not_stale() -> None:
    """Simulate the age-based (row_count > 0) branch directly rather than hitting a real DB."""
    calls = {"n": 0}

    class _FakeCursor:
        def execute(self, *_a: Any, **_k: Any) -> None:
            calls["n"] += 1

        def fetchone(self) -> tuple[Any, ...]:
            # 1: pg_class existence check. 2: exact COUNT(*) (real rows). 3: latest date row.
            if calls["n"] == 1:
                return (1,)
            if calls["n"] == 2:
                return (1998,)
            return (date(2026, 8, 17),)

    monitor = PipelineHealth()
    # "updated_at" (not "changed_at") - matches what _infer_date_column actually picks for
    # this table in production (its candidate list is date/updated_at/last_updated_at/
    # created_at/date_added; "changed_at" is a real column on this table too, but isn't a
    # candidate _infer_date_column tries).
    health = monitor.check_table_health(_FakeCursor(), "algo_config_audit", "updated_at", sla_days=7)

    assert health.status == HealthStatus.DEPRECATED
    # Must NOT use the generic "deprecated loader" wording - this table is actively written,
    # just event-driven with no guaranteed cadence.
    assert health.error_message is not None
    assert "deprecated loader" not in health.error_message.lower()
    assert "event-driven" in health.error_message.lower()
    assert health.is_healthy
