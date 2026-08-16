"""Regression test for the 2026-08-16 fix: OptimalLoader._run_serial()'s per-symbol loop
never wrote incremental progress to data_loader_status - completion_pct/symbols_loaded were
only ever set once, at the very end of the run (_update_final_status).

Every consumer that reads completion_pct mid-run (market.py's ">30min and <5% complete ->
TIMEOUT" heuristic among them) therefore saw a frozen 0% for the *entire* duration of any
serial per-symbol loader, misreporting long-but-healthy runs as stuck/timed-out. Live-confirmed
on company_info_sec: a 90-minute SEC backfill sat at completion_pct=0.00/symbols_loaded=0 in
data_loader_status the whole time, while its own log showed real progress ("Progress:
2500/4922"). StatusManager.update_progress() already existed for exactly this but was never
called from this loop - this test pins that it now is, at the same i%100 cadence as the
existing log line.
"""

from unittest.mock import MagicMock

from utils.optimal_loader import OptimalLoader


class _TestLoader(OptimalLoader):
    table_name = "signal_quality_scores"  # any real SAFE_TABLES entry


def _make_loader(num_symbols: int) -> _TestLoader:
    loader = _TestLoader.__new__(_TestLoader)
    loader.table_name = "signal_quality_scores"
    loader._status_manager = MagicMock()
    loader._stats = MagicMock()
    loader._infrastructure = MagicMock()
    loader._infrastructure.check_shutdown_requested.return_value = False
    loader.load_symbol = MagicMock(return_value=None)
    loader._update_health_check = MagicMock()
    return loader


class TestSerialLoopWritesIncrementalProgress:
    def test_update_progress_called_at_100_symbol_cadence(self):
        symbols = [f"SYM{i}" for i in range(250)]
        loader = _make_loader(len(symbols))

        loader._run_serial(symbols)

        calls = loader._status_manager.update_progress.call_args_list
        assert len(calls) == 2  # fires at i=100 and i=200, not at the final partial 50

        first_call_kwargs = calls[0].kwargs
        assert first_call_kwargs["symbols_loaded"] == 100
        assert first_call_kwargs["symbol_count"] == 250
        assert first_call_kwargs["completion_pct"] == 100 / 250 * 100.0

        second_call_kwargs = calls[1].kwargs
        assert second_call_kwargs["symbols_loaded"] == 200
        assert second_call_kwargs["completion_pct"] == 200 / 250 * 100.0

    def test_update_progress_failure_does_not_abort_the_load(self):
        symbols = [f"SYM{i}" for i in range(150)]
        loader = _make_loader(len(symbols))
        loader._status_manager.update_progress.side_effect = RuntimeError("db hiccup")

        # Must not raise despite update_progress failing - it's best-effort telemetry,
        # not load-critical.
        loader._run_serial(symbols)

        assert loader.load_symbol.call_count == 150
