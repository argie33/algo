"""Regression test: Phase 8's market-hours guard must know about NYSE/NASDAQ early closes.

Previously the guard compared the current ET time directly against the fixed
MARKET_OPEN_TIME (9:30 AM) / MARKET_CLOSE_TIME (4:00 PM) constants, with no awareness of
early-close days (day before Independence Day, day after Thanksgiving, Christmas Eve),
which actually close at 1:00 PM ET. On those days, entries submitted between 1 PM and
4 PM ET would have been waved through as "market hours" while the market was genuinely
closed. Fixed by routing through MarketCalendar.is_market_open(), which is early-close
aware. EARLY_CLOSES lists 2026-07-02 (day before Independence Day) as an early close.
"""

from datetime import date, datetime
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase8_entry_execution import run


def _base_kwargs(run_date=date(2026, 7, 2), execution_mode="paper"):
    return {
        "config": {"execution_mode": execution_mode},
        "run_date": run_date,
        "dry_run": True,
        "verbose": False,
        "log_phase_result_fn": MagicMock(),
    }


def test_blocks_entries_after_1pm_on_early_close_day():
    afternoon = datetime(2026, 7, 2, 14, 0)  # 2 PM ET, market already closed on an early-close day

    with patch("algo.orchestrator.phase8_entry_execution.datetime") as mock_dt:
        mock_dt.now.return_value = afternoon
        mock_dt.combine = datetime.combine

        result = run(**_base_kwargs())

    assert result.status == "blocked"
    assert result.halted is False
    assert result.data["entered"] == 0
    assert "market hours" in result.error.lower()
    assert "1:00 pm" in result.error.lower()


def test_does_not_block_before_1pm_on_early_close_day():
    """Sanity check: the market-hours guard itself must not fire before the early close -
    only reaching a later guard/step confirms this one passed."""
    late_morning = datetime(2026, 7, 2, 11, 0)  # 11 AM ET, still open on an early-close day

    with patch("algo.orchestrator.phase8_entry_execution.datetime") as mock_dt:
        mock_dt.now.return_value = late_morning
        mock_dt.combine = datetime.combine

        result = run(**_base_kwargs())

    assert not (result.status == "blocked" and "market hours" in (result.error or "").lower())
