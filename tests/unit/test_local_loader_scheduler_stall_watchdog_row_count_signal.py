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

TEST DESIGN 2026-08-16 (rewritten): a companion fix added a `deadline` param to
_monitor_loader_progress() - once `time.time() >= deadline`, the call returns True and hands
control back to the caller, independent of the stall signals. That gives these tests a clean,
deterministic way to prove "kept polling without deciding hung" - set deadline just past the
last scripted observation and assert the call returns True right there - instead of the
previous approach of exhausting a finite mock into a KeyboardInterrupt, which silently
depended on the exact number of DB round-trips per iteration and broke (hung indefinitely)
the moment that call count changed for any reason.
"""

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_scheduler_module():
    spec = importlib.util.spec_from_file_location(
        "local_loader_scheduler_under_test_stall", REPO_ROOT / "scripts" / "local_loader_scheduler.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_monitor(module, pct_sequence, row_count_sequence, time_sequence, deadline, max_stall_sec=300):
    """Drive _monitor_loader_progress() through an exact, fully-scripted sequence of poll
    results and time values - no open-ended padding or exception-exhaustion tricks. Every
    `time.time()`/`fetchone()` call this run will make must be accounted for in
    time_sequence/pct_sequence/row_count_sequence, or the mock raises StopIteration and the
    test fails loudly instead of hanging.

    proc.poll() always returns None (process still running) - this suite is scoped to the
    stall-detection signals, not the process-exit short-circuit."""
    read_cur = MagicMock()
    results = [
        val
        for pct, count in zip(pct_sequence, row_count_sequence, strict=True)
        for val in ((pct, "2026-08-16"), (count,))
    ]
    # _monitor_loader_progress() probes information_schema.columns for an 'updated_at' column
    # once, before the polling loop starts - stub that first fetchone() call as "no such
    # column" (None) so has_updated_at stays False and this suite only exercises the pct/
    # row-count signals it's scoped to, not the separate updated_at tertiary signal.
    read_cur.fetchone.side_effect = [None, *results]

    def fake_db_context(mode, **kwargs):
        ctx = MagicMock()
        ctx.__enter__.return_value = read_cur
        ctx.__exit__.return_value = False
        return ctx

    fake_proc = MagicMock()
    fake_proc.poll.return_value = None

    with (
        patch.object(module, "all_tables", return_value=["earnings_calendar"]),
        patch.object(module, "DatabaseContext", side_effect=fake_db_context),
        patch.object(module.time, "sleep", return_value=None),
        patch.object(module.time, "time", side_effect=time_sequence),
    ):
        return module._monitor_loader_progress(
            "load_earnings_calendar.py",
            fake_proc,
            deadline,
            poll_interval_sec=30,
            max_stall_sec=max_stall_sec,
        )


class TestStallWatchdogRowCountSignal:
    def test_zero_pct_but_growing_row_count_is_not_killed(self):
        """The exact false-positive this fix targets: completion_pct never leaves 0, but the
        table is visibly growing (real work happening) - must keep polling, not kill.

        Poll 1 @ t=30: pct=0, rows=100 (first observation, both stall timers reset to t=30).
        Poll 2 @ t=800 (>300s later): pct=0, rows=250 - row count grew, resetting the row
        stall timer, so is_stalled stays False even though the pct-only stall_duration alone
        would exceed max_stall_sec. Poll 3 @ t=801 hits the deadline before another DB round
        trip - proves the loop was still healthy, not that it happened to run out of script."""
        module = _load_scheduler_module()
        result = _run_monitor(
            module,
            pct_sequence=[0, 0],
            row_count_sequence=[100, 250],
            time_sequence=[0, 0, 0, 30, 800, 801],
            deadline=801,
            max_stall_sec=300,
        )
        assert result is True

    def test_zero_pct_and_frozen_row_count_is_killed(self):
        """Genuine hang: neither signal moves - must still be caught.

        Poll 1 @ t=30: pct=0, rows=100. Poll 2 @ t=800 (>300s later): pct=0, rows=100
        (unchanged) - real stall, returns False before the deadline (set far in the future,
        since this test is only exercising stall detection) is ever relevant."""
        module = _load_scheduler_module()
        result = _run_monitor(
            module,
            pct_sequence=[0, 0],
            row_count_sequence=[100, 100],
            time_sequence=[0, 0, 0, 30, 800],
            deadline=float("inf"),
            max_stall_sec=300,
        )
        assert result is False

    def test_advancing_pct_is_not_killed_even_with_frozen_row_count(self):
        """Loaders that DO call update_progress() (technical_data_daily,
        value_quality_growth) must keep working exactly as before this fix.

        Poll 1 @ t=30: pct=0, rows=100 (first observation). Poll 2 @ t=800: pct=25 - nonzero
        progress short-circuits straight to the next iteration (`continue`) without even
        checking row count, resetting the pct stall timer. Poll 3 @ t=801 hits the deadline -
        proves it kept going, not that it stalled and got lucky with the assertion."""
        module = _load_scheduler_module()
        result = _run_monitor(
            module,
            pct_sequence=[0, 25],
            row_count_sequence=[100, 100],
            time_sequence=[0, 0, 0, 30, 800, 801],
            deadline=801,
            max_stall_sec=300,
        )
        assert result is True
