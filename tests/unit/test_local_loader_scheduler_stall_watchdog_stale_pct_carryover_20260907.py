"""Regression test for the bug found 2026-09-07 (/goal session - "get this working" locally):
`_monitor_loader_progress()`'s stall condition required `last_pct <= 0.0`, which made it
structurally unable to ever declare a stall for any loader whose `completion_pct` was left
nonzero by its OWN PREVIOUS successful run - `data_loader_status.completion_pct` isn't reset
to 0/NULL at the start of a new run, so the very first poll reads that stale carryover value,
permanently failing the stall AND-condition regardless of row_count/updated_at.

Live-confirmed: `analyst_sentiment_analysis` (completion_pct nonzero from every healthy prior
run) sat with zero CPU, zero network connections, and a frozen table (no new rows, no
updated_at movement) for 58+ minutes while this watchdog never fired - exactly the scenario the
row-count/updated_at fallback signals (2026-08-16 fix) were added to catch, but the `<=0.0`
gate silently defeated them.

Fixed by dropping the `last_pct <= 0.0` requirement - `stall_duration` (time since last_pct
last *changed*) is itself already the correct staleness signal; requiring the value to also be
<=0 was never needed and just broke the fallback signals for any loader with completion_pct
history.

NOTE ON MOCK SEQUENCING: unlike the zero-pct case (test_local_loader_scheduler_stall_watchdog_
row_count_signal.py), a nonzero `current_pct` that just *changed* (including the very first
poll, where it changes from the initial `None`) hits the `if current_pct > 0: continue` fast
path and skips the row-count query for that tick entirely - so `fetchone.side_effect` here is
listed call-by-call (not paired 1:1 per iteration) to match that control flow exactly.
"""

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_scheduler_module():
    spec = importlib.util.spec_from_file_location(
        "local_loader_scheduler_under_test_stale_pct", REPO_ROOT / "scripts" / "local_loader_scheduler.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_monitor(module, fetchone_results, time_sequence, deadline, max_stall_sec=300):
    read_cur = MagicMock()
    # First fetchone() probes information_schema.columns for 'updated_at' - stub "no such
    # column" (None) so has_updated_at stays False and this suite only exercises the pct/
    # row-count signals it's scoped to, not the separate updated_at tertiary signal.
    read_cur.fetchone.side_effect = [None, *fetchone_results]

    def fake_db_context(mode, **kwargs):
        ctx = MagicMock()
        ctx.__enter__.return_value = read_cur
        ctx.__exit__.return_value = False
        return ctx

    fake_proc = MagicMock()
    fake_proc.poll.return_value = None

    with (
        patch.object(module, "all_tables", return_value=["analyst_sentiment_analysis"]),
        patch.object(module, "DatabaseContext", side_effect=fake_db_context),
        patch.object(module.time, "sleep", return_value=None),
        patch.object(module.time, "time", side_effect=time_sequence),
    ):
        return module._monitor_loader_progress(
            "load_analyst_sentiment_analysis.py",
            fake_proc,
            deadline,
            poll_interval_sec=30,
            max_stall_sec=max_stall_sec,
        )


class TestStallWatchdogStalePctCarryover:
    def test_stale_nonzero_pct_with_frozen_row_count_is_killed(self):
        """completion_pct=91 throughout (leftover from a prior successful run, never actually
        changes during this run) - before the fix, `last_pct <= 0.0` was always False here, so
        is_stalled could never become True no matter how long row_count stayed frozen.

        Poll 1 @ t=30: pct=91, changed from init None, >0 -> continue (row count NOT queried).
        Poll 2 @ t=331: pct=91, unchanged -> falls through -> row count queried for the first
        time (100) -> "changed" from None, so its own timer resets to t=331.
        Poll 3 @ t=800 (469s after t=331): pct=91 unchanged; row count queried again, still 100
        (genuinely frozen) -> row_stall_duration=469>300 and stall_duration=770>300 -> real
        stall, must return False.
        """
        module = _load_scheduler_module()
        result = _run_monitor(
            module,
            fetchone_results=[
                (91, "2026-09-07"),  # poll 1: pct query only (continue)
                (91, "2026-09-07"),  # poll 2: pct query
                (100,),  # poll 2: row count query (first read)
                (91, "2026-09-07"),  # poll 3: pct query
                (100,),  # poll 3: row count query (unchanged -> stall)
            ],
            time_sequence=[0, 0, 0, 30, 331, 800],
            deadline=float("inf"),
            max_stall_sec=300,
        )
        assert result is False

    def test_stale_nonzero_pct_with_growing_row_count_is_not_killed(self):
        """Same stale-nonzero completion_pct, but the table is genuinely still growing (real
        work happening) - must keep polling, not kill, exactly like the zero-pct case.

        Poll 1 @ t=30: pct=91 -> continue. Poll 2 @ t=331: pct=91 unchanged, row count first
        read = 100. Poll 3 @ t=800: pct=91 unchanged, row count = 250 (grew -> resets row
        timer, not stalled). Poll 4 @ t=801 hits the deadline before another DB round trip -
        proves the loop was still healthy.
        """
        module = _load_scheduler_module()
        result = _run_monitor(
            module,
            fetchone_results=[
                (91, "2026-09-07"),  # poll 1: pct query only (continue)
                (91, "2026-09-07"),  # poll 2: pct query
                (100,),  # poll 2: row count query (first read)
                (91, "2026-09-07"),  # poll 3: pct query
                (250,),  # poll 3: row count query (grew - still healthy)
            ],
            time_sequence=[0, 0, 0, 30, 331, 800, 801],
            deadline=801,
            max_stall_sec=300,
        )
        assert result is True
