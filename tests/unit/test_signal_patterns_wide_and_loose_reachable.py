#!/usr/bin/env python3
"""Regression test for a 2026-08-23 fix in algo/signals/signal_patterns.py::classify_base_type().

The "wide_and_loose" chart pattern (IBD's term for a deeper/looser-than-ideal but still
recognized base, roughly 35-50% depth) was structurally unreachable since the file's first
commit: classify_base_type()'s early-return gate (`if not base_info.get("in_base"): return
{"type": "no_base", ...}`) always fired before a later `if depth > 35: return {"type":
"wide_and_loose", ...}` branch could ever run, because base_detection()'s own `in_base` formula
already requires `depth <= BASE_MAX_DEPTH_PCT (35)` to be True - so `depth > 35` inside that
later branch was never satisfiable. Live-caught on UEC (base_depth_pct=42.5) and CDZI (44.8),
both permanently classified "no_base" instead of the more specific, more useful "wide_and_loose".

Fixed by intercepting the depth in the early-return gate itself (before base_info.get("in_base")
forces a generic no_base), using a new BASE_WIDE_LOOSE_MAX_DEPTH_PCT=50.0 ceiling. The old
`depth > 35` branch inside the closure is now correctly deleted as permanently-dead code rather
than just relabeled - reaching that closure at all already requires in_base=True, which already
requires depth<=35.
"""

from unittest.mock import MagicMock

from algo.signals.signal_patterns import SignalPatternsMixin


class TestWideAndLooseReachable:
    def _mixin_with_base_detection(self, base_depth_pct, in_base=False):
        mixin = SignalPatternsMixin()
        mixin.base_detection = MagicMock(
            return_value={
                "in_base": in_base,
                "base_depth_pct": base_depth_pct,
                "weeks_in_base": 20,
                "pivot_high": 42.0,
                "pct_to_pivot": 12.0,
                "breakout_imminent": False,
                "volume_dryup": False,
            }
        )
        return mixin

    def test_depth_just_above_max_classifies_wide_and_loose(self):
        mixin = self._mixin_with_base_detection(42.5)
        result = mixin.classify_base_type("UEC", "2026-08-21")
        assert result["type"] == "wide_and_loose"
        assert result["quality"] == "D"
        assert result["depth_pct"] == 42.5
        assert result.get("data_unavailable") is not True

    def test_depth_at_upper_band_boundary_classifies_wide_and_loose(self):
        mixin = self._mixin_with_base_detection(50.0)
        result = mixin.classify_base_type("BOUND", "2026-08-21")
        assert result["type"] == "wide_and_loose"

    def test_depth_just_beyond_band_falls_to_no_base(self):
        mixin = self._mixin_with_base_detection(50.1)
        result = mixin.classify_base_type("TOOWIDE", "2026-08-21")
        assert result["type"] == "no_base"
        assert result["reason"] == "pattern_not_detected"

    def test_deeply_extended_stock_still_no_base(self):
        mixin = self._mixin_with_base_detection(90.0)
        result = mixin.classify_base_type("FREEFALL", "2026-08-21")
        assert result["type"] == "no_base"

    def test_no_base_characteristics_do_not_leak_internal_price_history(self):
        mixin = SignalPatternsMixin()
        mixin.base_detection = MagicMock(
            return_value={
                "in_base": False,
                "base_depth_pct": 60.0,
                "weeks_in_base": 20,
                "pivot_high": 42.0,
                "pct_to_pivot": 12.0,
                "breakout_imminent": False,
                "volume_dryup": False,
                "_price_history": {
                    "highs": [1.0] * 130,
                    "lows": [1.0] * 130,
                    "closes": [1.0] * 130,
                    "volumes": [1.0] * 130,
                },
            }
        )
        result = mixin.classify_base_type("LEAKCHECK", "2026-08-21")
        assert result["type"] == "no_base"
        assert "_price_history" not in result["characteristics"]

    def test_in_base_true_never_hits_wide_and_loose_band(self):
        # Sanity: in_base=True with a depth inside the wide-and-loose band should be impossible
        # in real base_detection() output (in_base's own formula already caps depth at 35), but
        # if it somehow happened, classify_base_type must not treat it as wide_and_loose via the
        # early-return gate - it should fall through to real shape classification instead.
        # _price_history must be present here: base_detection() always populates it whenever
        # in_base=True (that's the invariant _classify_with_cursor's RuntimeError guards), so a
        # realistic mock of this scenario has to include it too.
        mixin = SignalPatternsMixin()
        mixin.base_detection = MagicMock(
            return_value={
                "in_base": True,
                "base_depth_pct": 40.0,
                "weeks_in_base": 20,
                "pivot_high": 42.0,
                "pct_to_pivot": 12.0,
                "breakout_imminent": False,
                "volume_dryup": False,
                "_price_history": {
                    "highs": [1.0] * 130,
                    "lows": [1.0] * 130,
                    "closes": [1.0] * 130,
                    "volumes": [1.0] * 130,
                },
            }
        )
        result = mixin.classify_base_type("SHOULDNOTHAPPEN", "2026-08-21")
        assert result["type"] != "wide_and_loose" or "characteristics" not in result
