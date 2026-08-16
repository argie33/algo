"""Regression test for the 2026-08-16 fix: _monitor_loader_progress() only ever checked
completion_pct to detect a hung loader, but completion_pct is written exactly once - at the
very end of OptimalLoader._update_final_status() - for ~38 of ~40 OptimalLoader subclasses
(only load_technical_indicators.py and load_value_quality_growth_metrics.py call
update_progress() mid-run). So completion_pct sits frozen at 0 for a loader's entire duration
regardless of whether it's actually working.

Live-confirmed 2026-08-16: earnings_calendar got killed with "hung at 0% for 1440s" while it
was steadily processing thousands of symbols the whole time (most returning "no earnings
dates found" - real work, just not the kind that advances completion_pct). Its own table's
MAX(updated_at) matched the kill timestamp almost exactly - genuine progress the watchdog
couldn't see.

Fixed by also tracking the primary table's own row count as a second liveness signal, and
only killing when BOTH completion_pct and row count are flat for max_stall_sec - preserves
detection of a truly hung process (nothing written anywhere) without false-killing one that's
writing rows but not calling update_progress().

NOTE ON TEST DESIGN: _monitor_loader_progress() is a `while True:` polling loop with no
"still healthy" return path - by design it only ever returns when tables are missing, the
status row disappears, or a real stall is detected. To assert "did NOT decide hung" within a
bounded number of poll iterations without actually looping forever, the mocked DB cursor
raises KeyboardInterrupt (not an Exception subclass, so it isn't swallowed by the function's
`except Exception: continue`) once the scripted iterations are exhausted - reaching that point
proves the function kept polling (didn't return False) through every iteration we fed it.
"""

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_scheduler_module():
    spec = importlib.util.spec_from_file_location(
        "local_loader_scheduler_under_test_stall", REPO_ROOT / "scripts" / "local_loader_scheduler.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_monitor(module, pct_sequence, row_count_sequence, time_sequence, max_stall_sec=300):
    """Drive _monitor_loader_progress() through a scripted sequence of poll results, then
    force a KeyboardInterrupt once exhausted so an unbounded "still healthy" loop can be
    observed without actually hanging the test."""
    read_cur = MagicMock()
    results = [
        val
        for pct, count in zip(pct_sequence, row_count_sequence, strict=True)
        for val in ((pct, "2026-08-16"), (count,))
    ]
    read_cur.fetchone.side_effect = [*results, KeyboardInterrupt("scripted iterations exhausted")]

    def fake_db_context(mode, **kwargs):
        ctx = MagicMock()
        ctx.__enter__.return_value = read_cur
        ctx.__exit__.return_value = False
        return ctx

    with (
        patch.object(module, "all_tables", return_value=["earnings_calendar"]),
        patch.object(module, "DatabaseContext", side_effect=fake_db_context),
        patch.object(module.time, "sleep", return_value=None),
        patch.object(module.time, "time", side_effect=time_sequence),
    ):
        return module._monitor_loader_progress(
            "load_earnings_calendar.py", poll_interval_sec=30, max_stall_sec=max_stall_sec
        )


class TestStallWatchdogRowCountSignal:
    def test_zero_pct_but_growing_row_count_is_not_killed(self):
        """The exact false-positive this fix targets: completion_pct never leaves 0, but the
        table is visibly growing (real work happening) - must keep polling, not kill."""
        module = _load_scheduler_module()
        # Poll 1 @ t=30: pct=0, rows=100 (first observation, no stall yet)
        # Poll 2 @ t=800 (>300s later): pct=0, rows=250 (rows grew -> resets row stall timer)
        with pytest.raises(KeyboardInterrupt):
            _run_monitor(
                module,
                pct_sequence=[0, 0],
                row_count_sequence=[100, 250],
                time_sequence=[0, 0, 30, 800],
                max_stall_sec=300,
            )

    def test_zero_pct_and_frozen_row_count_is_killed(self):
        """Genuine hang: neither signal moves - must still be caught."""
        module = _load_scheduler_module()
        # Poll 1 @ t=30: pct=0, rows=100
        # Poll 2 @ t=800 (>300s later): pct=0, rows=100 (unchanged) -> real stall, returns
        # before the KeyboardInterrupt sentinel is ever reached.
        hung = _run_monitor(
            module,
            pct_sequence=[0, 0],
            row_count_sequence=[100, 100],
            time_sequence=[0, 0, 30, 800],
            max_stall_sec=300,
        )
        assert hung is False

    def test_advancing_pct_is_not_killed_even_with_frozen_row_count(self):
        """Loaders that DO call update_progress() (technical_data_daily,
        value_quality_growth) must keep working exactly as before this fix."""
        module = _load_scheduler_module()
        with pytest.raises(KeyboardInterrupt):
            _run_monitor(
                module,
                pct_sequence=[0, 25],
                row_count_sequence=[100, 100],
                time_sequence=[0, 0, 30, 800],
                max_stall_sec=300,
            )
