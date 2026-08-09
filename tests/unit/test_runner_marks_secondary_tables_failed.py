"""Regression test: loaders/runner.py only marked a multi-table loader's secondary
output_tables (e.g. load_sector_industry_daily's sector_ranking/industry_ranking) via
mark_completed() on the SUCCESS path. On failure - either fail_rate exceeding the loader's
max_fail_rate, or an uncaught exception - only the primary table's status row was updated
(or, on a raw exception, not even that, since OptimalLoader.run() only marks itself). The
secondary tables kept whatever status they had from their last successful run, so a staleness
monitor or Phase 1 freshness check reading them would see a stale "completed" row and think
that day's run refreshed them when it never touched them at all.

Fixed by marking every entry in loader.output_tables as failed alongside the primary table
on both failure paths.
"""

from unittest.mock import patch

from utils.optimal_loader import OptimalLoader


class _RecordingStatusManager:
    calls = []  # class-level so both instances created during one run() call share state

    def __init__(self, table_name):
        self.table_name = table_name

    def mark_completed(self, **kwargs):
        _RecordingStatusManager.calls.append(("completed", self.table_name))

    def mark_failed(self, **kwargs):
        _RecordingStatusManager.calls.append(("failed", self.table_name))


class _FailRateExceededLoader(OptimalLoader):
    """Mirrors load_sector_industry_daily's shape: one primary table, N secondary output_tables.
    Every symbol 'fails' so fail_rate always exceeds max_fail_rate.

    Does NOT call OptimalLoader.__init__ (mirrors test_runner_uses_instance_table_name.py's
    fixture) since that constructs real DB-backed infra objects - unit tests only need the
    attributes run_loader() itself reads."""

    table_name = "sector_performance"
    output_tables = ["sector_performance", "sector_ranking", "industry_ranking"]
    primary_key = ("symbol",)
    watermark_field = "updated_at"
    max_fail_rate = 5.0
    exclude_etfs_from_symbols = False

    def __init__(self):
        pass

    def run(self, symbols, parallelism=1, backfill_days=None):
        return {"symbols_failed": len(symbols), "symbols_loaded": 0, "duration_sec": 1.0, "retry_count": 0}

    def close(self):
        pass


class _CrashingLoader(OptimalLoader):
    """Same multi-table shape, but run() raises instead of returning stats."""

    table_name = "sector_performance"
    output_tables = ["sector_performance", "sector_ranking", "industry_ranking"]
    primary_key = ("symbol",)
    watermark_field = "updated_at"
    max_fail_rate = 5.0
    exclude_etfs_from_symbols = False

    def __init__(self):
        pass

    def run(self, symbols, parallelism=1, backfill_days=None):
        raise RuntimeError("simulated API outage mid-load")

    def close(self):
        pass


def _run(monkeypatch, loader_class):
    import sys

    from loaders import runner

    monkeypatch.setattr(sys, "argv", ["run_loader.py", "--symbols", "AAPL,MSFT"])
    _RecordingStatusManager.calls = []
    with patch("utils.loaders.status_manager.LoaderStatusManager", _RecordingStatusManager):
        exit_code = runner.run_loader(loader_class)
    return exit_code, list(_RecordingStatusManager.calls)


def test_secondary_tables_marked_failed_when_fail_rate_exceeded(monkeypatch):
    exit_code, calls = _run(monkeypatch, _FailRateExceededLoader)

    assert exit_code == 1
    failed_tables = {table for status, table in calls if status == "failed"}
    assert failed_tables == {"sector_performance", "sector_ranking", "industry_ranking"}, (
        f"expected all 3 tables marked failed, got: {calls}"
    )


def test_secondary_tables_marked_failed_on_crash(monkeypatch):
    exit_code, calls = _run(monkeypatch, _CrashingLoader)

    assert exit_code == 1
    failed_secondary = {table for status, table in calls if status == "failed"}
    assert "sector_ranking" in failed_secondary
    assert "industry_ranking" in failed_secondary
