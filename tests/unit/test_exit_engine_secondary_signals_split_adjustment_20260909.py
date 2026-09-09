#!/usr/bin/env python3
"""Regression test for three secondary exit-trigger signals in ExitEngine, found via the
2026-09-09 real-money-readiness audit as the lower-priority sibling gap to
test_exit_engine_ema_stop_split_adjustment_20260909.py /
test_exit_engine_chandelier_hh_split_adjustment_20260909.py.

_is_pulling_back, _rs_line_breaking, and _eight_week_rule_active all read raw/unadjusted
price_daily prices over short lookback windows. A real stock split inside one of these
windows used to read as a fake single-day price jump, capable of false-triggering (or
masking) these confirmatory exit signals right after a legitimate split. Fixed by running
the same detect_and_adjust_splits() the primary stop calculations in this file already use.
"""

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

from algo.trading.exit_engine import ExitEngine

CONFIG: dict = {}


def _fake_self():
    return SimpleNamespace(config=dict(CONFIG))


class TestIsPullingBackAdjustsForSplits:
    def test_split_in_window_does_not_produce_bogus_pullback(self):
        """6-row window (most recent first, matches ORDER BY date DESC): a clean 2:1 split
        between the 3rd and 4th most-recent rows. Without adjustment, the pre-split high
        (~160) vs post-split close (~80) would read as a ~50% pullback - a false trigger.
        With adjustment, the real day-to-day pullback (a few %) must not trigger."""
        cur = MagicMock()
        # (close, high), most recent first.
        cur.fetchall.return_value = [
            (80.5, 81.0),  # today
            (80.0, 80.5),
            (79.5, 80.5),
            (80.0, 80.0),  # split boundary: prior close 160.0 -> this close 80.0 = 2:1
            (159.0, 160.0),
            (158.0, 159.0),
        ]
        result = ExitEngine._is_pulling_back(_fake_self(), cur, "SPLITSYM", date(2026, 9, 9))
        assert result is False, "a few-percent real pullback must not be masked as a huge fake one either way"

    def test_no_split_normal_pullback_detected(self):
        cur = MagicMock()
        cur.fetchall.return_value = [
            (95.0, 96.0),  # today: pulled back >2% from the 100 high
            (99.0, 100.0),
            (98.0, 99.0),
            (97.0, 98.0),
            (96.0, 97.0),
            (95.0, 96.0),
        ]
        result = ExitEngine._is_pulling_back(_fake_self(), cur, "NOSPLITSYM", date(2026, 9, 9))
        assert result is True


class TestRsLineBreakingAdjustsForSplits:
    def test_split_in_window_does_not_produce_bogus_break(self):
        """60-row window (most recent first): a clean 2:1 split partway through, with the
        underlying (split-adjusted) price otherwise perfectly flat, isolating the effect of
        the split itself from any real trend. Without adjustment, the pre-split ~160 level
        vs post-split ~80 level would corrupt the 50dma average against the current ratio
        (a fake break well past the 1% threshold); with adjustment, the ratio series is
        exactly flat, so it must not read as breaking at all."""
        spy = 500.0
        post_split = [(80.0, spy)] * 10
        pre_split = [(160.0, spy)] * 50  # same underlying value, pre-split scale
        rows = post_split + pre_split  # most-recent first, matches ORDER BY date DESC
        rows_with_date = [(date(2026, 9, 9), c, s) for c, s in rows]

        cur = MagicMock()
        cur.fetchall.return_value = rows_with_date
        result = ExitEngine._rs_line_breaking(_fake_self(), cur, "SPLITSYM", date(2026, 9, 9))
        assert result is False

    def test_no_split_detects_real_break(self):
        spy = 500.0
        # Most recent (today) is the lowest close, older days progressively higher - a real
        # recent decline putting today's ratio well below the 50dma of the preceding days.
        rows = [(50.0 + i * 0.5, spy) for i in range(51)]  # most-recent first (today=50, lowest)
        rows_with_date = [(date(2026, 9, 9), c, s) for c, s in rows]
        cur = MagicMock()
        cur.fetchall.return_value = rows_with_date
        result = ExitEngine._rs_line_breaking(_fake_self(), cur, "NOSPLITSYM", date(2026, 9, 9))
        assert result is True


class TestEightWeekRuleAdjustsForSplits:
    def test_split_in_window_does_not_produce_bogus_gain(self):
        """entry_price is already split-adjusted (as a live position's stored entry_price
        would be after _apply_split_adjustment). Without adjusting the window's raw closes,
        a split partway through the window would make MAX(close) read as a huge fake gain
        relative to the already-adjusted entry_price."""
        cur = MagicMock()
        # Ascending by date: 3 pre-split closes (~100), then a 2:1 split down to ~50.
        cur.fetchall.return_value = [(100.0,), (101.0,), (102.0,), (50.5,), (51.0,)]
        result = ExitEngine._eight_week_rule_active(
            _fake_self(),
            cur,
            "SPLITSYM",
            current_date=date(2026, 9, 9),
            entry_price=48.0,  # already split-adjusted, close to the post-split window prices
            days_held=60,
            threshold_pct=15.0,
            window_days=21,
        )
        # Split-adjusted max close in window (~51) vs entry_price 48 is a real ~6% gain,
        # below the 15% threshold - must not read as a bogus ~110% gain from the raw MAX(102).
        assert result is False

    def test_no_split_detects_real_gain(self):
        cur = MagicMock()
        cur.fetchall.return_value = [(100.0,), (105.0,), (120.0,)]
        result = ExitEngine._eight_week_rule_active(
            _fake_self(),
            cur,
            "NOSPLITSYM",
            current_date=date(2026, 9, 9),
            entry_price=100.0,
            days_held=60,
            threshold_pct=15.0,
            window_days=21,
        )
        assert result is True  # 20% gain >= 15% threshold
