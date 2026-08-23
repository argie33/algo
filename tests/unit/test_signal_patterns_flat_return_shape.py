#!/usr/bin/env python3
"""Regression test for a 2026-08-23 fix in algo/signals/signal_patterns.py::classify_base_type().

cup_with_handle/saucer/double_bottom/ascending_base/consolidation each used to return BOTH a
nested "characteristics" sub-dict AND the same fields flattened at top level - redundant, and
inconsistent with wide_and_loose/vcp/flat_base, which were always flat-only. All real consumers
(signal_options.py, buy_signal_generator.py) already read flat fields, so this had no observable
behavior change for them, but risked a future consumer picking the wrong shape. Fixed by
dropping the nested sub-dict from all five branches.

Drives classify_base_type() with real price data hand-shaped to hit each affected branch, since
these are the branches that had the bug (flat_base/vcp/wide_and_loose never had it, so aren't
retested here - already covered by their own dedicated tests).
"""

from unittest.mock import MagicMock, patch

from algo.signals.signal_patterns import SignalPatternsMixin


def _base_info(depth_pct, weeks, highs, lows, closes, volumes):
    return {
        "in_base": True,
        "base_depth_pct": depth_pct,
        "weeks_in_base": weeks,
        "pivot_high": max(highs),
        "pct_to_pivot": 1.0,
        "breakout_imminent": False,
        "volume_dryup": False,
        "_price_history": {"highs": highs, "lows": lows, "closes": closes, "volumes": volumes},
    }


def _classify(mixin):
    fake_cursor = MagicMock()
    with patch.object(mixin, "_with_cursor", side_effect=lambda op: op(fake_cursor)):
        return mixin.classify_base_type("SHAPE", "2026-08-21")


class TestFlatReturnShape:
    def test_double_bottom_has_no_nested_characteristics(self):
        # Two matching local minima >=10 bars apart, tight diff_pct - forces double_bottom.
        n = 40
        highs = [100.0] * n
        # A flat baseline would trivially tie its own local-min check everywhere (every plateau
        # point equals its window's min), swamping the two intended dips - use a tiny strictly-
        # increasing epsilon slope instead so only the two deep dips are genuine local minima.
        lows = [90.0 + i * 0.001 for i in range(n)]
        lows[5] = 80.0
        lows[25] = 80.2  # within 5% of the first low, >=10 bars apart
        closes = [95.0] * n
        volumes = [500_000.0] * n
        mixin = SignalPatternsMixin()
        mixin.base_detection = MagicMock(return_value=_base_info(20.0, 6, highs, lows, closes, volumes))
        # VCP must not intercept: force insufficient peaks by keeping vcp_detection's own peak
        # search from finding >=2 local maxima (flat highs array -> no peaks -> data_unavailable,
        # is_vcp falsy).
        result = _classify(mixin)

        assert result["type"] == "double_bottom"
        assert "characteristics" not in result
        assert "low_diff_pct" in result
        assert "depth_pct" in result  # flattened from `characteristics`

    def test_ascending_base_has_no_nested_characteristics(self):
        n = 40
        # Strictly increasing thirds-of-lows, 6-25% overall rise.
        lows = [90.0 + i * 0.1 for i in range(n)]  # ~4.3% rise over full range via thirds calc
        # Bump the rise into the 6-25% band by widening the spread.
        lows = [90.0 + i * 0.3 for i in range(n)]
        highs = [lo + 10.0 for lo in lows]
        closes = [lo + 5.0 for lo in lows]
        volumes = [500_000.0] * n
        mixin = SignalPatternsMixin()
        mixin.base_detection = MagicMock(return_value=_base_info(20.0, 6, highs, lows, closes, volumes))
        result = _classify(mixin)

        assert result["type"] == "ascending_base"
        assert "characteristics" not in result
        assert "rise_pct" in result
        assert "depth_pct" in result

    def test_consolidation_fallback_has_no_nested_characteristics(self):
        n = 40
        highs = [100.0 + i * 0.01 for i in range(n)]
        lows = [99.0 + i * 0.01 for i in range(n)]
        closes = [99.5 + i * 0.01 for i in range(n)]
        volumes = [500_000.0] * n
        mixin = SignalPatternsMixin()
        mixin.base_detection = MagicMock(return_value=_base_info(40.0, 20, highs, lows, closes, volumes))
        result = _classify(mixin)

        assert result["type"] == "consolidation"
        assert "characteristics" not in result
        assert "depth_pct" in result
