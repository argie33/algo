"""Regression test for the --expect-high-fail-rate opt-in flag.

Context: a targeted --symbols rerun against a deliberately curated hard bucket (e.g. the
residual Missing-XBRL buckets - SPACs, foreign private issuers, structurally-exempt filers)
legitimately hits a high data_unavailable rate. loaders/runner.py's max_fail_rate gate exists
to catch a REAL incomplete load against the full active universe, so applying it unchanged to
a curated subset falsely marks the table FAILED, polluting consecutive_failures and triggering
Phase 1 failsafe's automatic retry (algo/orchestrator/phase1_failsafe_retry.py) for what is
actually expected, correct behavior. Live-reproduced 2026-09-11 via
load_value_quality_growth_metrics.py (64.7%/46.1% data_unavailable on a 102-symbol targeted
rerun).

Fixed via an explicit opt-in flag (--expect-high-fail-rate), never inferred from --symbols
alone - a plain --symbols run against normal symbols that unexpectedly fail must still
fail-fast (see test_runner_marks_secondary_tables_failed.py and
test_runner_mark_completed_respects_max_fail_rate.py, both of which use --symbols without the
opt-in and must keep failing/passing on their own real fail rates).
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


class _CuratedHardBucketLoader(OptimalLoader):
    """Mirrors ValueQualityGrowthMetricsLoader's shape: declares the expect_high_fail_rate
    class attribute (same pattern as OptimalLoader's own sparse_symbol_population) so
    runner.py's hasattr() check sets it from --expect-high-fail-rate before calling run().
    65% of symbols fail, far above max_fail_rate=20% - exactly the shape of the live
    2026-09-11 repro."""

    table_name = "value_metrics"
    primary_key = ("symbol",)
    watermark_field = "updated_at"
    max_fail_rate = 20.0
    exclude_etfs_from_symbols = False
    expect_high_fail_rate = False

    def __init__(self):
        pass

    def run(self, symbols, parallelism=1, backfill_days=None):
        failed = round(len(symbols) * 0.65)
        return {
            "symbols_failed": failed,
            "symbols_loaded": len(symbols) - failed,
            "duration_sec": 1.0,
            "retry_count": 0,
        }

    def close(self):
        pass


def _run(monkeypatch, argv):
    import sys

    from loaders import runner

    monkeypatch.setattr(sys, "argv", argv)
    _RecordingStatusManager.calls = []
    with patch("utils.loaders.status_manager.LoaderStatusManager", _RecordingStatusManager):
        exit_code = runner.run_loader(_CuratedHardBucketLoader)
    return exit_code, list(_RecordingStatusManager.calls)


def test_high_fail_rate_without_opt_in_still_fails(monkeypatch):
    """Baseline: without --expect-high-fail-rate, a 65% fail rate against 20% max_fail_rate
    must still fail-fast - the opt-in must not change default behavior."""
    exit_code, calls = _run(monkeypatch, ["run_loader.py", "--symbols", "SYM1,SYM2,SYM3,SYM4"])

    assert exit_code == 1
    assert any(status == "failed" for status, *_ in calls), f"expected a failed mark, got: {calls}"


def test_high_fail_rate_with_opt_in_does_not_fail(monkeypatch):
    """With --expect-high-fail-rate, the same 65% fail rate must NOT be marked FAILED, and
    min_completion_pct must be relaxed so LoaderStatusManager.mark_completed()'s own internal
    safety check doesn't silently re-demote it either."""
    exit_code, calls = _run(
        monkeypatch,
        ["run_loader.py", "--symbols", "SYM1,SYM2,SYM3,SYM4", "--expect-high-fail-rate"],
    )

    assert exit_code == 0, f"expected PASS under --expect-high-fail-rate, got calls: {calls}"
    assert not any(status == "failed" for status, *_ in calls), (
        f"expected no failed mark under --expect-high-fail-rate, got: {calls}"
    )
    completed = {table: kwargs for table, kwargs in calls if table != "failed"}
    assert completed["value_metrics"]["min_completion_pct"] == 0.0, (
        f"expected min_completion_pct relaxed to 0.0 so mark_completed()'s own safety check "
        f"doesn't re-demote this to FAILED, got: {completed['value_metrics']}"
    )
