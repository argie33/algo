#!/usr/bin/env python3
"""Regression test for ExitEngine._chandelier_or_ema_stop's 21-EMA branch, found via the
2026-09-09 real-money-readiness audit.

price_daily stores raw/unadjusted prices. The 21-EMA branch used to feed raw closes
straight into the EMA with no split adjustment, so a real stock split inside the 30-row
lookback window read as a fake single-day step, producing a stop price with no relationship
to the post-split price - in the reproduction below, a stop price ABOVE the current price,
which would fire immediately as a false stop-out on a real open position right after a
legitimate split. Fixed by running the same detect_and_adjust_splits() the offline
technical_data_daily loader already uses (loaders/technical_indicators.py) on the fetched
closes before computing the EMA.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from algo.trading.exit_engine import ExitEngine

CONFIG = {
    "switch_to_21ema_after_days": 10,
    "chandelier_atr_mult": 3.0,
}


def _fake_self():
    return SimpleNamespace(config=dict(CONFIG))


def _mock_cursor_ema(closes):
    cur = MagicMock()
    cur.fetchall.return_value = [(c,) for c in closes]
    return cur


class TestChandelierOrEmaStopAdjustsForSplits:
    def test_clean_2for1_split_in_window_produces_stop_below_current_price(self):
        """30-row window: 20 pre-split closes ending at 164.0, then a clean 2:1 split down
        to 82.0 for the remaining 10 rows. Without split adjustment the EMA stays anchored
        near the pre-split ~150-160 level, producing a stop well ABOVE the post-split
        current price (~85) - a false stop-out waiting to fire. With adjustment, the stop
        must land below the current price, like any sane trailing stop."""
        pre_split = [
            150.0,
            151.0,
            149.5,
            152.0,
            153.0,
            154.0,
            152.5,
            155.0,
            156.0,
            157.0,
            158.0,
            156.5,
            159.0,
            160.0,
            161.0,
            160.5,
            162.0,
            163.0,
            161.5,
            164.0,
        ]
        post_split = [82.0, 82.5, 83.0, 82.8, 83.5, 84.0, 83.7, 84.2, 84.5, 85.0]
        closes = pre_split + post_split
        assert len(closes) == 30
        current_price = closes[-1]

        cur = _mock_cursor_ema(closes)
        stop = ExitEngine._chandelier_or_ema_stop(_fake_self(), cur, "SPLITSYM", None, days_held=15)

        assert stop is not None
        assert stop < current_price, (
            f"split-adjusted 21-EMA stop ({stop}) must be below the post-split current "
            f"price ({current_price}) - a stop above current price means the position "
            f"would be stopped out immediately on a legitimate split, not a real decline"
        )
        # Sanity: adjusted stop should be in the same order of magnitude as the post-split
        # price, not anywhere near the pre-split ~150-160 level.
        assert 70.0 < stop < 90.0

    def test_no_split_still_computes_normally(self):
        """No split in the window - detect_and_adjust_splits() must be a no-op, matching
        pre-fix behavior exactly for the common case."""
        closes = [100.0 + i * 0.1 for i in range(30)]
        cur = _mock_cursor_ema(closes)
        stop = ExitEngine._chandelier_or_ema_stop(_fake_self(), cur, "NOSPLITSYM", None, days_held=15)
        assert stop is not None
        assert stop == stop  # not NaN
        assert 95.0 < stop < 105.0
