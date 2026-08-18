"""Regression test: _run_symbol_pass must report live progress to data_loader_status, not
leave completion_pct frozen at 0 for the entire run.

Bug (found 2026-08-18, loader-health review): the per-symbol loop tracked
loader._stats.increment("symbols_processed"/"symbols_failed") in memory every symbol, but
never called _status_manager.update_progress() - so data_loader_status.completion_pct stayed
frozen at the 0 mark_running() set it to, for this loader's entire run (up to the 540m/9h SLA
timeout), indistinguishable from a hang on the dashboard. Live-confirmed: a real run 22
minutes in already showed real row_count (66K-163K rows across the combo tables) while
completion_pct still read 0.00 - same "frozen at 0%" bug class already fixed for other
loaders this week (e.g. load_enhanced_quality_growth_metrics.py's own DASHBOARD ACCURACY
FIX). Fixed by calling update_progress() on the existing every-50-symbols cadence (the
database health check already ran on that cadence).
"""

from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import _run_symbol_pass


class _FakeStats:
    def __init__(self):
        self.counts: dict[str, int] = {}

    def increment(self, key: str) -> None:
        self.counts[key] = self.counts.get(key, 0) + 1


class _FakeShutdownWatcher:
    def check_shutdown_requested(self) -> bool:
        return False


class _FakeStatusManager:
    def __init__(self):
        self.calls: list[dict] = []

    def update_progress(self, symbols_loaded=None, symbol_count=None, completion_pct=None):
        self.calls.append(
            {"symbols_loaded": symbols_loaded, "symbol_count": symbol_count, "completion_pct": completion_pct}
        )


class _FakeLoader:
    table_name = "annual_income_statement"

    def __init__(self):
        self._stats = _FakeStats()
        self._status_manager = _FakeStatusManager()
        self.processed: list[str] = []

    def load_symbol(self, symbol: str) -> None:
        self.processed.append(symbol)
        self._stats.increment("symbols_processed")


class TestFinancialStatementsProgressReporting:
    def test_update_progress_called_every_50_symbols_not_left_frozen(self):
        loader = _FakeLoader()
        symbols = [f"SYM{i}" for i in range(120)]

        with patch("loaders.load_financial_statements.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = MagicMock()
            mock_db_ctx.return_value.__exit__.return_value = False
            _run_symbol_pass(
                active=[loader],
                symbols=symbols,
                shutdown_watcher=_FakeShutdownWatcher(),
                start=__import__("time").time(),
            )

        assert loader._status_manager.calls, (
            "update_progress() was never called - completion_pct would stay frozen at 0 "
            "for the loader's entire run, indistinguishable from a hang on the dashboard"
        )
        # 120 symbols at every-50 cadence -> calls at i=50, i=100 (2 calls).
        assert len(loader._status_manager.calls) == 2
        assert loader._status_manager.calls[0]["symbols_loaded"] == 50
        assert loader._status_manager.calls[0]["symbol_count"] == 120
        assert loader._status_manager.calls[0]["completion_pct"] == round(100.0 * 50 / 120, 2)
        # Progress must actually advance, not report the same stale value twice.
        assert loader._status_manager.calls[1]["completion_pct"] > loader._status_manager.calls[0]["completion_pct"]

    def test_progress_update_failure_does_not_abort_the_pass(self):
        """Progress reporting is diagnostic, not load-bearing - a transient status-table
        write failure must not stop real data loading."""
        loader = _FakeLoader()

        def _raise(*args, **kwargs):
            raise RuntimeError("simulated status-table write failure")

        loader._status_manager.update_progress = _raise
        symbols = [f"SYM{i}" for i in range(60)]

        with patch("loaders.load_financial_statements.DatabaseContext") as mock_db_ctx:
            mock_db_ctx.return_value.__enter__.return_value = MagicMock()
            mock_db_ctx.return_value.__exit__.return_value = False
            _run_symbol_pass(
                active=[loader],
                symbols=symbols,
                shutdown_watcher=_FakeShutdownWatcher(),
                start=__import__("time").time(),
            )

        assert len(loader.processed) == 60, "a progress-update failure must not abort real symbol processing"
