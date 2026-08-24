"""Regression test: Phase 8's price-freshness revalidation (_check_price_data_freshness) must
be early-close and weekend/holiday aware, matching the fix already applied to
phase1_data_freshness.py::_compute_pipeline_context and to this same file's own separate
entry-time market-hours guard (test_phase8_market_hours_early_close.py).

Previously this function's own market-context computation was a naive hardcoded hour check
(`now_et.hour > 9 or ...` / `now_et.hour >= 16`) despite its docstring explicitly claiming to
match Phase 1's logic - it never got either fix. On a NYSE/NASDAQ early close (real close
1:00 PM ET: day before July 4th, day after Thanksgiving, Christmas Eve), this stayed in
INTRADAY context until 4:00 PM, expecting yesterday's close as the freshness baseline for 3
hours after today's close had already posted - right before Phase 8 submits real entry orders.
"""

from datetime import date, datetime
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase8_entry_execution import _check_price_data_freshness


def test_early_close_day_expects_todays_close_by_2pm_not_4pm():
    """2026-07-02 (day before Independence Day) closes at 1:00 PM ET - by 2 PM the trading
    day has genuinely ended and today's close should already be the expected freshness
    baseline, not yesterday's."""
    run_date = date(2026, 7, 2)
    afternoon = datetime(2026, 7, 2, 14, 0)  # 2 PM ET

    with patch("algo.orchestrator.phase8_entry_execution.DatabaseContext") as mock_db:
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (date(2026, 7, 2),)  # today's close already loaded
        mock_db.return_value.__enter__.return_value = mock_cur

        is_fresh, msg = _check_price_data_freshness(run_date, now_et=afternoon)

    assert is_fresh is True


def test_early_close_day_still_expects_yesterdays_close_before_1pm():
    """Sanity check: before the early close, the guard must still correctly expect
    yesterday's close (INTRADAY context), not fire early."""
    run_date = date(2026, 7, 2)
    late_morning = datetime(2026, 7, 2, 11, 0)  # 11 AM ET, still open

    with patch("algo.orchestrator.phase8_entry_execution.DatabaseContext") as mock_db:
        mock_cur = MagicMock()
        # Yesterday's close (2026-07-01) is the correct INTRADAY-context baseline.
        mock_cur.fetchone.return_value = (date(2026, 7, 1),)
        mock_db.return_value.__enter__.return_value = mock_cur

        is_fresh, msg = _check_price_data_freshness(run_date, now_et=late_morning)

    assert is_fresh is True


def test_normal_day_still_uses_4pm_boundary():
    """A regular trading day (not an early close) must keep the standard 4 PM boundary -
    at 2 PM on a normal day, yesterday's close is still the correct INTRADAY baseline."""
    run_date = date(2026, 7, 6)  # a normal Monday
    afternoon = datetime(2026, 7, 6, 14, 0)  # 2 PM ET, market still open on a normal day

    with patch("algo.orchestrator.phase8_entry_execution.DatabaseContext") as mock_db:
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (date(2026, 7, 3),)  # last trading day before the 7/4 weekend
        mock_db.return_value.__enter__.return_value = mock_cur

        is_fresh, msg = _check_price_data_freshness(run_date, now_et=afternoon)

    assert is_fresh is True
