#!/usr/bin/env python3
"""Regression test for ExitEngine._eight_week_rule_active, found via a systematic sweep
for the NaN-comparison-guard bug class on 2026-08-10 (after fuzzing found 9 other
instances this session).

`entry_price <= 0` doesn't catch NaN. Lower severity than the trading paths (NaN
cascades through Decimal division to a NaN gain_pct, then `gain_pct >= threshold_pct`
is always False for NaN, so this fails toward NOT triggering the 8-week hold rule rather
than a dangerous silent accept) - fixed for consistency with the rest of this file's
_chandelier_or_ema_stop, already fixed earlier this session.

Tests call the method directly against a lightweight fake `self` (just a `.config`-free
call since this method takes no config), with a mocked cursor.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from algo.trading.exit_engine import ExitEngine


def _mock_cursor(max_close):
    cur = MagicMock()
    cur.fetchone.return_value = (max_close,)
    return cur


class TestEightWeekRuleRejectsNanEntryPrice:
    def test_nan_entry_price_raises(self):
        cur = _mock_cursor(120.0)
        with pytest.raises(ValueError, match="Invalid entry price"):
            ExitEngine._eight_week_rule_active(
                SimpleNamespace(),
                cur,
                "CHAOSFUZZ",
                current_date=None,
                entry_price=float("nan"),
                days_held=60,
                threshold_pct=20.0,
                window_days=21,
            )

    def test_infinite_entry_price_raises(self):
        cur = _mock_cursor(120.0)
        with pytest.raises(ValueError, match="Invalid entry price"):
            ExitEngine._eight_week_rule_active(
                SimpleNamespace(),
                cur,
                "CHAOSFUZZ",
                current_date=None,
                entry_price=float("inf"),
                days_held=60,
                threshold_pct=20.0,
                window_days=21,
            )

    def test_normal_entry_price_still_works(self):
        cur = _mock_cursor(120.0)
        result = ExitEngine._eight_week_rule_active(
            SimpleNamespace(),
            cur,
            "AAPL",
            current_date=None,
            entry_price=100.0,
            days_held=60,
            threshold_pct=15.0,
            window_days=21,
        )
        assert result is True  # 20% gain >= 15% threshold
