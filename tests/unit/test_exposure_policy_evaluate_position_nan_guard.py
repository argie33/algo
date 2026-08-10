#!/usr/bin/env python3
"""Regression test for ExposurePolicy._evaluate_position, found via a systematic sweep
for the NaN-comparison-guard bug class on 2026-08-10 (13 more instances found this sweep,
across reconciliation.py, position_monitor.py, phase3/6/8/9, exposure_policy.py,
executor_exit_handler.py).

`risk_per_share <= 0` / `cur_price_float <= 0` don't catch NaN (NaN comparisons are
always False in Python) - this gates force_exit_negative_r and other tier-based risk
decisions for a real open position.
"""

from datetime import date
from unittest.mock import MagicMock

import pytest

from algo.risk.exposure_policy import ExposurePolicy


def _row(**overrides):
    base = dict(
        trade_id="TRD-1",
        symbol="AAPL",
        entry_price=100.0,
        init_stop=90.0,
        t1_price=None,
        t2_price=None,
        t3_price=None,
        trade_date=date(2026, 1, 1),
        position_id=1,
        qty=10,
        target_hits=0,
        cur_stop=90.0,
        cur_price=110.0,
        pnl_pct=0.0,
    )
    base.update(overrides)
    return tuple(base.values())


class TestEvaluatePositionRejectsNan:
    def test_nan_entry_price_rejected_via_risk_per_share(self):
        with pytest.raises(ValueError):
            ExposurePolicy._evaluate_position(MagicMock(), _row(entry_price=float("nan")), tier={})

    def test_nan_cur_price_rejected(self):
        with pytest.raises(ValueError):
            ExposurePolicy._evaluate_position(MagicMock(), _row(cur_price=float("nan")), tier={})

    def test_infinite_entry_price_rejected(self):
        with pytest.raises(ValueError):
            ExposurePolicy._evaluate_position(MagicMock(), _row(entry_price=float("inf")), tier={})
