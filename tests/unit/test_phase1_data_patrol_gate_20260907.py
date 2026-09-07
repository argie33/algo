"""Regression test for the 2026-09-07 fix in algo/orchestrator/phase1_data_freshness.py:
_check_data_patrol_results() now actually queries data_patrol_log and halts on CRITICAL/ERROR
findings from the most recent DataPatrol run, AND halts when patrol data is missing/stale
(closing the terraform-documented "fail-open... Phase 1 passes vacuously" gap too) - unless
the caller opts into ALLOW_MISSING_DATA_PATROL for local/dev testing. Closes a gap where this
module's own docstring ("ISSUE #6 FIX: Integrate DataPatrol checks to block Phase 1") and
terraform's DataPatrol step comment both described this behavior, but no code anywhere in
algo/orchestrator/ or algo/orchestration/ ever queried the table. See
_check_data_patrol_results's docstring for the live-confirmed evidence (4 CRITICAL staleness
findings on a local dev run that Phase 1 ignored).
"""

from datetime import timedelta
from unittest.mock import MagicMock

from algo.orchestrator.phase1_data_freshness import _check_data_patrol_results


def _make_log_fn():
    calls = []

    def log_phase_result_fn(*args, **kwargs):
        calls.append((args, kwargs))

    log_phase_result_fn.calls = calls
    return log_phase_result_fn


class TestCheckDataPatrolResults:
    def test_no_rows_at_all_halts_by_default(self):
        cur = MagicMock()
        cur.fetchone.return_value = None
        log_fn = _make_log_fn()

        result = _check_data_patrol_results(cur, log_fn)

        assert result is not None
        assert result.halted is True
        assert result.data["reason"] == "no_patrol_data"

    def test_no_rows_at_all_warns_when_allowed(self):
        cur = MagicMock()
        cur.fetchone.return_value = None
        log_fn = _make_log_fn()

        result = _check_data_patrol_results(cur, log_fn, allow_missing_patrol=True)

        assert result is None
        assert any("warning" in call[0] for call in log_fn.calls)

    def test_stale_patrol_run_halts_by_default(self):
        cur = MagicMock()
        cur.fetchone.side_effect = [
            ("run-1", "2026-09-06T00:00:00"),  # latest patrol_run_id, created_at
            (timedelta(hours=20),),  # age past the 8h freshness window
        ]
        log_fn = _make_log_fn()

        result = _check_data_patrol_results(cur, log_fn)

        assert result is not None
        assert result.halted is True
        assert result.data["reason"] == "stale_patrol_data"

    def test_stale_patrol_run_warns_when_allowed(self):
        cur = MagicMock()
        cur.fetchone.side_effect = [
            ("run-1", "2026-09-06T00:00:00"),
            (timedelta(hours=20),),
        ]
        log_fn = _make_log_fn()

        result = _check_data_patrol_results(cur, log_fn, allow_missing_patrol=True)

        assert result is None
        assert any("freshness window" in str(call).lower() for call in log_fn.calls)

    def test_fresh_run_with_no_blocking_findings_passes(self):
        cur = MagicMock()
        cur.fetchone.side_effect = [
            ("run-2", "2026-09-07T12:00:00"),
            (timedelta(hours=1),),
        ]
        cur.fetchall.return_value = []
        log_fn = _make_log_fn()

        result = _check_data_patrol_results(cur, log_fn)

        assert result is None

    def test_fresh_run_with_critical_findings_halts(self):
        cur = MagicMock()
        cur.fetchone.side_effect = [
            ("run-3", "2026-09-07T12:58:28"),
            (timedelta(minutes=5),),
        ]
        cur.fetchall.return_value = [
            ("staleness", "price_daily", "price_daily stale: 3d > 1d threshold"),
            ("staleness", "technical_data_daily", "technical_data_daily stale: 3d > 1d threshold"),
        ]
        log_fn = _make_log_fn()

        result = _check_data_patrol_results(cur, log_fn)

        assert result is not None
        assert result.halted is True
        assert result.status == "halted"
        assert "price_daily" in result.data["findings"][0]

    def test_fresh_run_with_critical_findings_halts_even_when_missing_data_allowed(self):
        """allow_missing_patrol only covers the no-data/stale-data cases - it must never
        downgrade a real CRITICAL/ERROR finding to a warning."""
        cur = MagicMock()
        cur.fetchone.side_effect = [
            ("run-3", "2026-09-07T12:58:28"),
            (timedelta(minutes=5),),
        ]
        cur.fetchall.return_value = [
            ("staleness", "price_daily", "price_daily stale: 3d > 1d threshold"),
        ]
        log_fn = _make_log_fn()

        result = _check_data_patrol_results(cur, log_fn, allow_missing_patrol=True)

        assert result is not None
        assert result.halted is True

    def test_query_exception_does_not_halt(self):
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("connection reset")
        log_fn = _make_log_fn()

        result = _check_data_patrol_results(cur, log_fn)

        assert result is None
