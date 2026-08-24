"""Regression test: Phase 1's pipeline_context computation (algo/orchestrator/
phase1_data_freshness.py::_compute_pipeline_context) must know about NYSE/NASDAQ early
closes, and about weekends/holidays at all.

Previously this was two hardcoded checks with no MarketCalendar awareness:
- is_market_open = now_et.hour > 9 or (now_et.hour == 9 and now_et.minute >= 30) - no upper
  bound (true 9:30 AM through midnight every day) and no trading-day check, so weekends/
  holidays were misclassified as INTRADAY during 9:30 AM-4 PM.
- is_after_market_close = now_et.hour >= 16 - no early-close awareness. On the day before
  July 4th / day after Thanksgiving / Christmas Eve (real close 1:00 PM ET), this stayed
  False until 4 PM, 3 hours after the trading day had genuinely ended.

Fixed by delegating to MarketCalendar.is_market_open()/is_early_close() (the same fix
already applied once for phase8_entry_execution.py's own market-hours guard - see
test_phase8_market_hours_early_close.py - and once inside MarketCalendar itself, per that
module's own "this was previously wrong by 2 hours" comment).
"""

from datetime import datetime, time

from algo.orchestrator.phase1_data_freshness import _compute_pipeline_context


def test_early_close_day_is_eod_context_by_1pm_not_4pm():
    """2026-07-02 (day before Independence Day) closes at 1:00 PM ET - by 2 PM the trading
    day has genuinely ended and pipeline_context must already read EOD."""
    afternoon = datetime(2026, 7, 2, 14, 0)  # 2 PM ET

    is_market_open, is_after_close, context, market_close_time = _compute_pipeline_context(afternoon)

    assert is_market_open is False
    assert is_after_close is True
    assert context == "EOD"
    assert market_close_time == time(13, 0)


def test_early_close_day_still_intraday_before_1pm():
    """Sanity check: the fix must not fire early - 11 AM on the same early-close day is
    still genuinely open."""
    late_morning = datetime(2026, 7, 2, 11, 0)  # 11 AM ET

    is_market_open, is_after_close, context, market_close_time = _compute_pipeline_context(late_morning)

    assert is_market_open is True
    assert is_after_close is False
    assert context == "INTRADAY"
    assert market_close_time == time(13, 0)


def test_normal_day_still_closes_at_4pm():
    """A regular trading day (not an early close) must keep the standard 4 PM boundary."""
    afternoon = datetime(2026, 7, 6, 15, 0)  # 3 PM ET, a normal Monday

    is_market_open, is_after_close, context, market_close_time = _compute_pipeline_context(afternoon)

    assert is_market_open is True
    assert is_after_close is False
    assert context == "INTRADAY"
    assert market_close_time == time(16, 0)


def test_weekend_is_not_misclassified_as_intraday():
    """The old check had no trading-day awareness at all - 11 AM on a Saturday must not
    read as INTRADAY (implying live trading) just because the wall-clock hour is in the
    9:30 AM-4 PM range."""
    saturday = datetime(2026, 7, 4, 11, 0)  # Saturday, also a market holiday

    is_market_open, is_after_close, context, _market_close_time = _compute_pipeline_context(saturday)

    assert is_market_open is False
    assert context != "INTRADAY"
