"""Regression test: loaders/runner.py's post-run success path called
LoaderStatusManager.mark_completed() without min_completion_pct, so it fell back to
mark_completed()'s own hardcoded 98% default when re-deriving completion_pct - even though
this same function had, moments earlier, already verified the run against the loader's REAL
max_fail_rate and decided to PASS it. Any loader with max_fail_rate > 2% (quality/growth/value
metrics: 20%, financial statements: 15%, etc.) that legitimately lands between
(100-max_fail_rate)% and 98% would pass runner.py's own fail-rate gate, then get immediately
flipped back to FAILED by this redundant, stricter re-check - contradicting the PASS verdict
just computed.

Fixed by passing min_completion_pct=max(0, 100-max_fail_rate) to both the primary table's and
any output_tables' mark_completed() calls on the success path, keeping them consistent with the
fail-rate gate that already ran.
"""

from unittest.mock import patch

from utils.optimal_loader import OptimalLoader


class _RecordingStatusManager:
    calls = []  # class-level so all instances created during one run() call share state

    def __init__(self, table_name):
        self.table_name = table_name

    def mark_completed(self, **kwargs):
        _RecordingStatusManager.calls.append((self.table_name, kwargs))

    def mark_failed(self, **kwargs):
        _RecordingStatusManager.calls.append(("failed", self.table_name, kwargs))


class _PartialFailureWithinToleranceLoader(OptimalLoader):
    """15% of symbols fail, but max_fail_rate=20% - this run should PASS."""

    table_name = "quality_metrics"
    output_tables = ["quality_metrics", "growth_metrics"]
    primary_key = ("symbol",)
    watermark_field = "updated_at"
    max_fail_rate = 20.0
    exclude_etfs_from_symbols = False

    def __init__(self):
        pass

    def run(self, symbols, parallelism=1, backfill_days=None):
        failed = round(len(symbols) * 0.15)
        return {
            "symbols_failed": failed,
            "symbols_loaded": len(symbols) - failed,
            "duration_sec": 1.0,
            "retry_count": 0,
        }

    def close(self):
        pass


def test_success_path_mark_completed_uses_loaders_own_threshold(monkeypatch):
    import sys

    from loaders import runner

    monkeypatch.setattr(sys, "argv", ["run_loader.py", "--symbols", ",".join(f"SYM{i}" for i in range(20))])
    _RecordingStatusManager.calls = []
    with patch("utils.loaders.status_manager.LoaderStatusManager", _RecordingStatusManager):
        exit_code = runner.run_loader(_PartialFailureWithinToleranceLoader)

    assert exit_code == 0, "15% failure with 20% max_fail_rate must PASS runner's own gate"

    completed_calls = {table: kwargs for table, kwargs in _RecordingStatusManager.calls if table != "failed"}
    assert "quality_metrics" in completed_calls, f"expected a mark_completed call, got: {_RecordingStatusManager.calls}"
    assert completed_calls["quality_metrics"].get("min_completion_pct") == 80.0, (
        f"primary table's mark_completed() must pass min_completion_pct=80.0 (100-max_fail_rate), "
        f"got kwargs: {completed_calls['quality_metrics']} - without this it silently falls back to "
        f"mark_completed()'s own 98% default and would flip this legitimately-passing run to FAILED"
    )
    assert "growth_metrics" in completed_calls, (
        f"expected secondary table also marked, got: {_RecordingStatusManager.calls}"
    )
    assert completed_calls["growth_metrics"].get("min_completion_pct") == 80.0, (
        f"secondary (output_tables) mark_completed() must also pass the loader's real threshold, "
        f"got kwargs: {completed_calls['growth_metrics']}"
    )
