#!/usr/bin/env python3
"""Regression test for ExitEngine._chandelier_or_ema_stop, found via fuzzing with
pathological inputs on 2026-08-10.

A NaN close price (21-EMA branch) or NaN highest-high/ATR (chandelier branch) silently
propagated through Decimal arithmetic - Decimal NaN doesn't raise on arithmetic or
quantize(), it just produces another NaN - to return a NaN trailing STOP PRICE for a real
open position, with zero exception raised anywhere in this path.

Same bug class already found and fixed this session in position_sizer.py,
utils/validation/financial.py, and phase8_entry_execution.py's
_calculate_dynamic_stop_loss. This one is arguably the most safety-critical instance: a
NaN trailing stop feeding into a real exit decision for an open position is a direct
risk-management failure, not just a data-quality nuisance.

Tests call _chandelier_or_ema_stop directly against a lightweight fake `self` (just a
`.config` dict) rather than a full ExitEngine instance, since the method only reads
self.config and the full constructor pulls in TradeExecutor/Alpaca credentials
unnecessarily for this pure calculation test.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

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


def _mock_cursor_chandelier(hh, atr):
    cur = MagicMock()
    cur.fetchone.return_value = (hh, atr)
    return cur


class TestChandelierOrEmaStopRejectsNan:
    def test_ema_branch_nan_close_price_raises_not_silently_returns_nan(self):
        """days_held >= switch_to_21ema_after_days routes to the 21-EMA branch."""
        closes = [100.0] * 20 + [float("nan")]
        cur = _mock_cursor_ema(closes)
        with pytest.raises(ValueError, match="Invalid close price"):
            ExitEngine._chandelier_or_ema_stop(_fake_self(), cur, "CHAOSSYM", None, days_held=15)

    def test_ema_branch_normal_prices_still_work(self):
        closes = [100.0 + i * 0.1 for i in range(21)]
        cur = _mock_cursor_ema(closes)
        stop = ExitEngine._chandelier_or_ema_stop(_fake_self(), cur, "CHAOSSYM", None, days_held=15)
        assert stop is not None
        assert stop == stop  # not NaN
        assert stop > 0

    def test_chandelier_branch_nan_highest_high_raises(self):
        """days_held < switch_to_21ema_after_days routes to the chandelier branch."""
        cur = _mock_cursor_chandelier(hh=float("nan"), atr=2.0)
        with pytest.raises(ValueError, match="Invalid highest-high"):
            ExitEngine._chandelier_or_ema_stop(_fake_self(), cur, "CHAOSSYM", None, days_held=3)

    def test_chandelier_branch_nan_atr_raises(self):
        cur = _mock_cursor_chandelier(hh=100.0, atr=float("nan"))
        with pytest.raises(ValueError, match="Invalid ATR"):
            ExitEngine._chandelier_or_ema_stop(_fake_self(), cur, "CHAOSSYM", None, days_held=3)

    def test_chandelier_branch_infinite_atr_raises(self):
        cur = _mock_cursor_chandelier(hh=100.0, atr=float("inf"))
        with pytest.raises(ValueError, match="Invalid ATR"):
            ExitEngine._chandelier_or_ema_stop(_fake_self(), cur, "CHAOSSYM", None, days_held=3)

    def test_chandelier_branch_normal_values_still_work(self):
        cur = _mock_cursor_chandelier(hh=100.0, atr=2.0)
        stop = ExitEngine._chandelier_or_ema_stop(_fake_self(), cur, "CHAOSSYM", None, days_held=3)
        assert stop == 94.0  # 100 - 3*2
