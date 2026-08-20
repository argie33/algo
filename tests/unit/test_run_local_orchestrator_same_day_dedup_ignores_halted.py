"""Regression test: scripts/run_local_orchestrator.py's same-day dedup guard must not treat a
halted/errored prior attempt as "today's session already ran".

Live-confirmed 2026-08-20: a manual/debug invocation of `--evening` at 8:13 AM ET on 2026-08-19
(investigating a separate buy_sell_daily staleness issue) halted immediately at Phase 7 - no
orders placed, no reconciliation run. `_find_todays_run("evening", ...)` previously matched on
DATE(started_at) + run_id prefix alone, with no `overall_status` filter, so when the REAL
scheduled Task Scheduler run fired that evening at 5:30 PM ET, it found the halted row, printed
"Skipping EVENING: already ran today", and returned without calling Orchestrator.run() at all.
Task Scheduler recorded this as a clean success (exit code 0, "Last Result: 0") even though
nothing executed - algo_trades, circuit_breaker_status, and every other Phase 6/9 output stayed
frozen at the 3 PM PRECLOSE run for the rest of the day and into the next.

The fix restricts the dedup match to overall_status IN ('success', 'degraded') - the only
statuses that mean the run actually got through its phases and could have touched
entry/exit/reconciliation state. 'halted'/'error' mean an early guard stopped the run before it
did anything, so the real scheduled session must still be allowed to run.
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "lambda" / "algo_orchestrator"))


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "run_local_orchestrator_under_test", PROJECT_ROOT / "scripts" / "run_local_orchestrator.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = _load_module()


def _mock_db_context(fetchone_return):
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = fetchone_return
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False
    return mock_cur, mock_ctx


def test_sql_filters_to_success_and_degraded_statuses():
    """The dedup query itself must exclude halted/error rows, not just filter in Python -
    otherwise ORDER BY ... LIMIT 1 could still return a halted row that sorts most recent."""
    mock_cur, mock_ctx = _mock_db_context(None)
    with patch("utils.db.DatabaseContext", return_value=mock_ctx):
        MODULE._find_todays_run("evening", MODULE.date(2026, 8, 19))

    sql = mock_cur.execute.call_args[0][0]
    assert "overall_status IN ('success', 'degraded')" in sql, (
        "same-day dedup query must restrict to overall_status IN ('success', 'degraded') so a "
        "halted/errored prior attempt (which executed no phases) doesn't block the real "
        "scheduled run from executing"
    )


def test_halted_prior_run_does_not_count_as_todays_session():
    """A halted-only day (matching the live 2026-08-19 EVENING incident) must return None so the
    real scheduled run proceeds, not the halted run's row."""
    # SQL-level filtering means the halted row is never returned by the query in the first
    # place - simulate that by returning no row.
    _, mock_ctx = _mock_db_context(None)
    with patch("utils.db.DatabaseContext", return_value=mock_ctx):
        result = MODULE._find_todays_run("evening", MODULE.date(2026, 8, 19))

    assert result is None, (
        "a day with only a halted/errored prior run for this run_type must not be treated as "
        "already run - the real scheduled session must still execute"
    )


def test_successful_prior_run_still_blocks_same_day_rerun():
    """The original anti-duplicate-trade protection must still work for a genuinely completed run."""
    row = ("LOCAL-EVENING-20260819-173000-000000", "success", "2026-08-19 21:30:00")
    _, mock_ctx = _mock_db_context(row)
    with patch("utils.db.DatabaseContext", return_value=mock_ctx):
        result = MODULE._find_todays_run("evening", MODULE.date(2026, 8, 19))

    assert result is not None
    assert result["run_id"] == "LOCAL-EVENING-20260819-173000-000000"
