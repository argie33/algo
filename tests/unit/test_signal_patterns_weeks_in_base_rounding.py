#!/usr/bin/env python3
"""Regression test for a 2026-08-23 fix in algo/signals/signal_patterns.py::base_detection().

weeks_in_base = len(base_highs) // 5 truncated instead of rounding to the nearest week. Every
duration>=N gate in classify_base_type() compares against a whole number (flat_base needs
duration>=5, cup/saucer need duration>=7), so a base sitting just under a "//5" boundary (e.g.
34 bars = 6.8 weeks) was truncated down to 6 and could miss a >=7 gate it should have cleared.
Fixed by using round(bars/5) (nearest whole week, zero decimal places) instead of floor division
- round(x, 1) would NOT fix this, since every gate compares against a whole number and 6.8 still
fails a >=7 check either way; only zero-decimal rounding changes the outcome at the margin.
"""

from unittest.mock import MagicMock, patch

from algo.signals.signal_patterns import SignalPatternsMixin


def _rows_for_bar_count(n, price=100.0, base_high=100.0):
    """n price_daily rows (date, high, low, close, volume), newest-first as the real query
    returns, shaped so base_detection()'s pivot-high search lands at index 0 (the whole window
    is the base) and volume-dryup's own 50-bar requirement doesn't interfere with the fields
    under test (weeks_in_base/base_depth_pct/in_base)."""
    return [(f"2026-01-{(n - i) % 28 + 1:02d}", base_high, base_high * 0.85, price, 500_000.0) for i in range(n)]


class TestWeeksInBaseRounding:
    def test_34_bars_rounds_up_to_7_weeks_not_6(self):
        mixin = SignalPatternsMixin()
        fake_cursor = MagicMock()
        # 34 total rows: BASE_MIN_BARS(10) excluded from the pre-breakout search leaves the
        # whole 34-bar window as the base (peak at index 0), matching base_highs length 34.
        fake_cursor.fetchall.return_value = list(reversed(_rows_for_bar_count(34)))
        with patch.object(mixin, "_with_cursor", side_effect=lambda op: op(fake_cursor)):
            result = mixin.base_detection("THIRTYFOUR", "2026-08-21")

        assert result["weeks_in_base"] == 7  # 34/5 = 6.8 -> rounds to 7, was floor()'d to 6

    def test_35_bars_stays_7_weeks_exact_multiple_unaffected(self):
        mixin = SignalPatternsMixin()
        fake_cursor = MagicMock()
        fake_cursor.fetchall.return_value = list(reversed(_rows_for_bar_count(35)))
        with patch.object(mixin, "_with_cursor", side_effect=lambda op: op(fake_cursor)):
            result = mixin.base_detection("THIRTYFIVE", "2026-08-21")

        assert result["weeks_in_base"] == 7
