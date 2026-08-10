#!/usr/bin/env python3
"""Regression test for SignalPatternsMixin.base_type_stop, found via a systematic sweep
for the NaN-comparison-guard bug class on 2026-08-10 (after fuzzing found 6 other
instances this session in position_sizer.py, financial.py, phase7/8, exit_engine.py, and
order_manager.py).

Both of this function's own safety checks - `candidate < floor_stop` (the 8% floor clamp)
and `candidate >= entry_price` (the intended "corrupted data" fail-fast diagnostic) - are
silently bypassed by a NaN candidate, since NaN comparisons are always False in Python.
`candidate` can go NaN if any upstream price_daily.low/pivot_high/consolidation_pct
feeding a base-type stop strategy was corrupted, and the resulting stop_price=nan would
propagate silently instead of surfacing the actual root cause this function already tries
to diagnose via its own "Indicates corrupt data" ValueError.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from algo.signals.signal_patterns import SignalPatternsMixin


def _mixin_with_nan_low_price():
    mixin = SignalPatternsMixin()
    fake_cursor = MagicMock()
    fake_cursor.fetchone.return_value = (float("nan"),)

    def fake_with_cursor(operation):
        return operation(fake_cursor)

    return mixin, fake_with_cursor


class TestBaseTypeStopRejectsNanCandidate:
    def test_nan_low_price_raises_corrupted_data_error_not_silent_nan_stop(self):
        mixin, fake_with_cursor = _mixin_with_nan_low_price()

        with (
            patch.object(mixin, "_with_cursor", side_effect=fake_with_cursor),
            patch.object(mixin, "classify_base_type", return_value={"type": "cup_with_handle"}),
            patch.object(mixin, "three_weeks_tight", return_value={"is_3wt": False}),
            patch.object(mixin, "high_tight_flag", return_value={"is_ht": False}),
        ):
            with pytest.raises(ValueError, match="non-finite"):
                mixin.base_type_stop("CHAOSFUZZ", date(2026, 8, 10), entry_price=100.0, atr=2.0)

    def test_normal_low_price_still_produces_valid_finite_stop(self):
        mixin = SignalPatternsMixin()
        fake_cursor = MagicMock()
        fake_cursor.fetchone.return_value = (95.0,)

        def fake_with_cursor(operation):
            return operation(fake_cursor)

        with (
            patch.object(mixin, "_with_cursor", side_effect=fake_with_cursor),
            patch.object(mixin, "classify_base_type", return_value={"type": "cup_with_handle"}),
            patch.object(mixin, "three_weeks_tight", return_value={"is_3wt": False}),
            patch.object(mixin, "high_tight_flag", return_value={"is_ht": False}),
        ):
            result = mixin.base_type_stop("AAPL", date(2026, 8, 10), entry_price=100.0, atr=2.0)

        assert result["stop_price"] == result["stop_price"]  # not NaN
        assert 0 < result["stop_price"] < 100.0
