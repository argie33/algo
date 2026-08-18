"""Regression test for the 2026-08-17 fix: etf_symbols reaped FAILED forever despite real
success on every retry, same regression class
`test_phase1_failsafe_retry_invokes_loader_main_not_generic_path.py` already covers for
"prices".

`4261cd620` fixed the NORMAL scheduled path by adding `output_tables = ["etf_symbols"]` to
`MarketConstituentsLoader` - but that only takes effect through loaders/runner.py's
global-mode branch (`main(MarketConstituentsLoader, global_mode=True)`), the only place that
copies the primary table's mark_completed() onto output_tables. MarketConstituentsLoader IS
an OptimalLoader subclass, so `_check_and_refresh_local()`'s in-process retry loop
(algo/orchestrator/phase1_failsafe_retry.py) fell through to instantiating the class directly
and calling `load_global()`, which only marks its OWN table (stock_symbols) COMPLETED and
never touches etf_symbols - live-reproduced repeatedly 2026-08-17 (consecutive_failures
climbing past 3 across several verification runs, all AFTER `4261cd620` landed): the loader
logged "Successfully refreshed etf_symbols table with 5611 ETF symbols" every time, but
etf_symbols' own data_loader_status row stayed FAILED from the original reap event, so this
retry loop kept reporting "not recovered" and re-queuing it forever despite correct data on
every attempt.

Note: etf_symbols has no date column of its own, so it's never reached via the
date-freshness scan (`loaders_to_refresh`) - it only ever enters the retry loop via the
separate FAILED/ERROR/TIMEOUT pre-check against data_loader_status (live-confirmed:
`[PHASE 1 FAILSAFE LOCAL] Found FAILED loader (will retry): etf_symbols`), so this test
simulates that path specifically via `fetchall()`, not the MAX(date) staleness path.

Fixed by adding "constituents" (etf_symbols' loader_key) to the same forced-main() special
case "financial_statements"/"prices" already had - forcing the retry to go through
`loaders/load_market_constituents.py`'s own main(), which invokes runner.py's
output_tables-aware global-mode branch.
"""

import datetime
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase1_failsafe_retry import _check_and_refresh_local


class _FailedEtfSymbolsCursor:
    """etf_symbols is FAILED in data_loader_status (the REAPED scenario); every
    date-freshness-scanned table reports fresh/complete, so only etf_symbols - via the
    separate FAILED-loader pre-check - reaches the retry loop."""

    def __init__(self):
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        if "FROM data_loader_status" in self._last_query:
            return [("etf_symbols", 3, "[REAPED] Stuck in RUNNING since ... exceeds 600s timeout")]
        return []

    def fetchone(self):
        # COUNT(*) completeness check for any date-freshness-scanned table.
        if "COUNT(*)" in self._last_query:
            return (100, 100)
        # SELECT MAX(date_col) FROM <table> for every date-freshness-scanned table: always
        # fresh, since this test is only exercising the FAILED-loader retry path.
        return (datetime.date(2026, 8, 17),)


class _FailedOnlyDatabaseContext:
    def __init__(self, cursor):
        self._cur = cursor

    def __enter__(self):
        return self._cur

    def __exit__(self, *exc):
        return False


def _make_fake_loader_module(main_return=0):
    """A fake `loaders.load_market_constituents`-like module exposing only main(), matching
    the shape the forced-main() special case expects."""
    module = MagicMock()
    module.main = MagicMock(return_value=main_return)
    module.__name__ = "loaders.load_market_constituents"
    return module


def _run_with_failed_etf_symbols(monkeypatch, mock_import_module, mock_status_mgr_factory):
    from algo.orchestrator import phase1_failsafe_retry as mod

    today = datetime.date(2026, 8, 17)
    cursor = _FailedEtfSymbolsCursor()
    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FailedOnlyDatabaseContext(cursor))
    monkeypatch.setattr(mod, "_get_expected_data_date", lambda **kwargs: (today, "EOD - test"))
    monkeypatch.setattr(mod, "LoaderStatusManager", mock_status_mgr_factory)

    with patch("importlib.import_module", mock_import_module):
        return _check_and_refresh_local(run_date=today, pipeline_context="EOD", dry_run=False)


class TestFailsafeRetryEtfSymbolsUsesMainPath:
    def test_invokes_market_constituents_main_directly_not_generic_load_global(self, monkeypatch):
        fake_module = _make_fake_loader_module(main_return=0)

        def mock_import(name, *a, **kw):
            if name == "loaders.load_market_constituents":
                return fake_module
            return MagicMock()

        mock_import_spy = MagicMock(side_effect=mock_import)
        mock_status_mgr = MagicMock()
        mock_status_mgr.get_status.return_value = {"status": "COMPLETED", "completion_pct": 100.0}

        _run_with_failed_etf_symbols(monkeypatch, mock_import_spy, lambda table: mock_status_mgr)

        constituents_calls = [
            c for c in mock_import_spy.call_args_list if c.args[0] == "loaders.load_market_constituents"
        ]
        assert len(constituents_calls) == 1, (
            "must import loaders.load_market_constituents (etf_symbols' loader_key "
            f"'constituents') exactly once - got calls: {mock_import_spy.call_args_list}"
        )
        assert fake_module.main.call_count == 1, (
            "must invoke load_market_constituents.py's own main() - the only path that runs "
            "through runner.py's output_tables-aware global-mode branch and marks etf_symbols "
            "COMPLETED - not instantiate MarketConstituentsLoader directly and call "
            "load_global(), which only marks stock_symbols and never touches etf_symbols"
        )

    def test_successful_refresh_is_reported_recovered(self, monkeypatch):
        """The regression itself: a successful main() run must actually clear etf_symbols'
        FAILED status, not leave it stuck forever despite correct data on every attempt."""
        fake_module = _make_fake_loader_module(main_return=0)

        def mock_import(name, *a, **kw):
            if name == "loaders.load_market_constituents":
                return fake_module
            return MagicMock()

        mock_import_spy = MagicMock(side_effect=mock_import)
        mock_status_mgr = MagicMock()
        mock_status_mgr.get_status.return_value = {"status": "COMPLETED", "completion_pct": 100.0}

        result = _run_with_failed_etf_symbols(monkeypatch, mock_import_spy, lambda table: mock_status_mgr)

        assert "etf_symbols" in result["recovered"]
        assert "etf_symbols" not in result["still_failing"]
