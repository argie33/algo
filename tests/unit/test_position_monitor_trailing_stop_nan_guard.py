#!/usr/bin/env python3
"""Regression test for PositionMonitor._compute_trailing_stop, found via a systematic
sweep for the NaN-comparison-guard bug class on 2026-08-10 (13 more instances found this
sweep, across reconciliation.py, position_monitor.py, phase3/6/8/9, exposure_policy.py,
executor_exit_handler.py).

`cur_price <= 0` / `active_stop <= 0` / `entry_price <= 0` don't catch NaN (NaN
comparisons are always False in Python) - this function controls the actual trailing-stop
price written to the DB for a real open position.
"""

from unittest.mock import MagicMock

import pytest

from algo.monitoring.position_monitor import PositionMonitor, PositionValidationError


def _call(**overrides):
    kwargs = {
        "entry_price": 100.0,
        "active_stop": 90.0,
        "cur_price": 110.0,
        "atr": 2.0,
        "sma_50": 105.0,
        "target_hits": 0,
    }
    kwargs.update(overrides)
    return PositionMonitor._compute_trailing_stop(MagicMock(), **kwargs)


class TestComputeTrailingStopRejectsNan:
    def test_nan_cur_price_rejected(self):
        with pytest.raises(PositionValidationError):
            _call(cur_price=float("nan"))

    def test_nan_active_stop_rejected(self):
        with pytest.raises(PositionValidationError):
            _call(active_stop=float("nan"))

    def test_nan_entry_price_rejected(self):
        with pytest.raises(PositionValidationError):
            _call(entry_price=float("nan"))

    def test_infinite_cur_price_rejected(self):
        with pytest.raises(PositionValidationError):
            _call(cur_price=float("inf"))

    def test_valid_inputs_still_pass(self):
        result = _call()
        assert isinstance(result, float)
