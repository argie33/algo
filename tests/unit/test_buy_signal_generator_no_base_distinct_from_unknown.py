#!/usr/bin/env python3
"""Regression test for a 2026-08-23 fix in algo/signals/buy_signal_generator.py::
_classify_base_type_safe().

classify_base_type() can return a definitive negative - {"type": "no_base",
"reason": "pattern_not_detected", data_unavailable: False} - meaning it successfully
determined the symbol is NOT currently in a chartable base (e.g. too far below its pivot
high to be consolidating). This is a real, computed finding, not missing data. Live-caught
2026-08-23 on UEC/CDZI: both got a clean {"type": "no_base", "characteristics": {"in_base":
False, "base_depth_pct": 42.5, ...}} result with no exception and data_unavailable=False,
yet _classify_base_type_safe() collapsed it to the exact same (None, None) returned for a
genuine data_unavailable/exception case - making an analytical result indistinguishable from
a real data gap on both the TUI (dashboard/panels/signals.py) and web (TradingSignals.jsx)
dashboards, both of which render None as a bare "--"/em-dash.

Fixed by mapping "no_base" through _BASE_TYPE_DISPLAY to "No Base" like every other pattern
type, reserving (None, None) for actual unknowns.
"""

from unittest.mock import MagicMock

from algo.signals.buy_signal_generator import BuySignalGenerator


class TestNoBaseDistinctFromUnknown:
    def test_no_base_returns_display_string_not_none(self):
        gen = BuySignalGenerator()
        gen._pattern_classifier = MagicMock()
        gen._pattern_classifier.classify_base_type.return_value = {
            "type": "no_base",
            "quality": "D",
            "data_unavailable": False,
            "reason": "pattern_not_detected",
            "characteristics": {"in_base": False, "base_depth_pct": 42.5, "weeks_in_base": 11},
        }

        display_name, base_length_days = gen._classify_base_type_safe("UEC", "2026-08-21")

        assert display_name == "No Base"
        assert base_length_days is None

    def test_genuine_data_unavailable_still_returns_none(self):
        gen = BuySignalGenerator()
        gen._pattern_classifier = MagicMock()
        gen._pattern_classifier.classify_base_type.return_value = {
            "type": None,
            "data_unavailable": True,
            "reason": "insufficient_price_history",
        }

        display_name, base_length_days = gen._classify_base_type_safe("NEWCO", "2026-08-21")

        assert display_name is None
        assert base_length_days is None

    def test_classifier_exception_still_returns_none(self):
        gen = BuySignalGenerator()
        gen._pattern_classifier = MagicMock()
        gen._pattern_classifier.classify_base_type.side_effect = RuntimeError("boom")

        display_name, base_length_days = gen._classify_base_type_safe("BROKEN", "2026-08-21")

        assert display_name is None
        assert base_length_days is None

    def test_real_pattern_still_maps_to_its_display_name(self):
        gen = BuySignalGenerator()
        gen._pattern_classifier = MagicMock()
        gen._pattern_classifier.classify_base_type.return_value = {
            "type": "double_bottom",
            "quality": "C",
            "duration_weeks": 7,
        }

        display_name, base_length_days = gen._classify_base_type_safe("KDP", "2026-08-21")

        assert display_name == "Double Bottom"
        assert base_length_days == 35
