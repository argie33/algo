"""Regression test for the 2026-08-10 fix: _check_and_refresh_local()'s retry loop
(algo/orchestrator/phase1_failsafe_retry.py) invoked `scripts/run_loader.py {loader_key}
--force-refresh`, the exact "generic path bypasses main()" bug class
scripts/local_loader_scheduler.py was already rearchitected away from earlier the same
session (see that module's own "ROOT-CAUSE FIX 2026-08-10" comment, which names "prices"
among the affected loaders).

run_loader.py's generic dispatch imports the loader CLASS and calls
`PriceLoader().run()` with default constructor args (interval="1d", asset_class="stock")
- it never reaches loaders/load_prices.py's own main(), the only code path that loops
over all 6 asset_class x interval combos. Live-reproduced: a "prices" refresh via the old
path exited 0 ("refreshed successfully") while etf_price_daily/price_weekly/
price_monthly/etf_price_weekly/etf_price_monthly were ALL marked FAILED at 0.00%
completion - only price_daily (matching the default constructor args) ever actually
loaded.

Fixed identically to local_loader_scheduler.py: invoke `python loaders/{file}.py`
directly. Also fixed a second, related bug: exit code 0 only means the subprocess didn't
crash, not that the specific table's own load succeeded - now re-checks the table's own
terminal status before reporting "recovered".
"""

import datetime
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase1_failsafe_retry import _check_and_refresh_local


class _StaleOnlyCursor:
    """etf_price_daily reports stale (5 days behind); every other configured table
    reports fresh, so only etf_price_daily reaches the retry loop."""

    def __init__(self, fresh: datetime.date, stale: datetime.date):
        self._fresh = fresh
        self._stale = stale
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchone(self):
        if "COUNT(*)" in self._last_query:
            if "FROM technical_data_daily" in self._last_query:
                return (100, 100, 100, 100, 100)
            return (100, 100)
        if "FROM etf_price_daily" in self._last_query:
            return (self._stale,)
        return (self._fresh,)


class _StaleOnlyDatabaseContext:
    def __init__(self, cursor):
        self._cur = cursor

    def __enter__(self):
        return self._cur

    def __exit__(self, *exc):
        return False


def _run_with_stale_etf(monkeypatch, mock_subprocess_run, mock_status_mgr_factory):
    from algo.orchestrator import phase1_failsafe_retry as mod

    fresh = datetime.date(2026, 8, 10)
    stale = datetime.date(2026, 8, 5)
    cursor = _StaleOnlyCursor(fresh, stale)
    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _StaleOnlyDatabaseContext(cursor))
    monkeypatch.setattr(mod, "_get_expected_data_date", lambda **kwargs: (fresh, "EOD - test"))
    monkeypatch.setattr(mod, "LoaderStatusManager", mock_status_mgr_factory)

    with patch("subprocess.run", mock_subprocess_run):
        return _check_and_refresh_local(run_date=fresh, pipeline_context="EOD", dry_run=False)


class TestFailsafeRetryInvokesLoaderMainDirectly:
    def test_invokes_loader_module_directly_not_run_loader_generic_path(self, monkeypatch):
        mock_run = MagicMock(return_value=MagicMock(returncode=0, stdout="", stderr=""))
        mock_status_mgr = MagicMock()
        mock_status_mgr.get_status.return_value = {"status": "COMPLETED", "completion_pct": 100.0}

        _run_with_stale_etf(monkeypatch, mock_run, lambda table: mock_status_mgr)

        assert mock_run.call_count == 1
        cmd = mock_run.call_args.args[0]
        assert len(cmd) == 2 and cmd[1] == "loaders/load_prices.py", (
            f"must invoke the loader module's own main() directly (`python "
            f"loaders/load_prices.py`), not the generic run_loader.py dispatch that "
            f"bypasses it - got {cmd}"
        )

    def test_exit_code_zero_but_table_not_completed_is_not_reported_recovered(self, monkeypatch):
        """The regression itself: a subprocess that exits 0 while THIS table's own
        status is FAILED (e.g. only price_daily loaded, etf_price_daily got 0.00%
        completion under its own safety check) must not be reported as recovered."""
        mock_run = MagicMock(return_value=MagicMock(returncode=0, stdout="", stderr=""))
        mock_status_mgr = MagicMock()
        mock_status_mgr.get_status.return_value = {
            "status": "FAILED",
            "completion_pct": 0.0,
            "error_message": "Cannot mark COMPLETED with only 0.00% completion (0/5 symbols)",
        }

        result = _run_with_stale_etf(monkeypatch, mock_run, lambda table: mock_status_mgr)

        assert "etf_price_daily" not in result["recovered"]
        assert "etf_price_daily" in result["still_failing"]

    def test_exit_code_zero_and_table_completed_is_reported_recovered(self, monkeypatch):
        mock_run = MagicMock(return_value=MagicMock(returncode=0, stdout="", stderr=""))
        mock_status_mgr = MagicMock()
        mock_status_mgr.get_status.return_value = {"status": "COMPLETED", "completion_pct": 100.0}

        result = _run_with_stale_etf(monkeypatch, mock_run, lambda table: mock_status_mgr)

        assert "etf_price_daily" in result["recovered"]
        assert "etf_price_daily" not in result["still_failing"]
