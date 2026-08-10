"""Regression tests for 5 NaN-comparison-guard gaps found 2026-08-10 in
loaders/compute_circuit_breakers.py (the dashboard-reporting mirror of
algo/risk/circuit_breaker.py, already fixed earlier the same day - this file had the same
gaps and was missed in that pass).

`value <= 0` never catches NaN (NaN comparisons are always False in Python) - these feed
circuit_breaker_status, which the dashboard health panel reads directly.
"""

from unittest.mock import MagicMock

import pytest

from loaders.compute_circuit_breakers import (
    _compute_daily_loss,
    _compute_drawdown,
    _compute_spy_change,
    _compute_weekly_loss,
)


class TestComputeDrawdownRejectsNaN:
    def test_nan_peak_raises(self):
        cur = MagicMock()
        cur.fetchone.return_value = {"peak": float("nan"), "current": 90_000.0}
        with pytest.raises(RuntimeError, match="Invalid peak/current"):
            _compute_drawdown(cur)

    def test_nan_current_raises(self):
        cur = MagicMock()
        cur.fetchone.return_value = {"peak": 100_000.0, "current": float("nan")}
        with pytest.raises(RuntimeError, match="Invalid peak/current"):
            _compute_drawdown(cur)

    def test_valid_values_still_compute(self):
        cur = MagicMock()
        cur.fetchone.return_value = {"peak": 100_000.0, "current": 90_000.0}
        assert _compute_drawdown(cur) == 10.0


class TestComputeDailyLossRejectsNaN:
    def test_nan_cur_val_raises(self):
        cur = MagicMock()
        cur.fetchone.side_effect = [
            {"adjusted_equity": float("nan")},
            {"adjusted_equity": 90_000.0},
        ]
        with pytest.raises(ValueError, match="Invalid adjusted_equity"):
            _compute_daily_loss(cur, __import__("datetime").date(2026, 8, 10))


class TestComputeWeeklyLossRejectsNaN:
    def test_nan_week_ago_raises(self):
        cur = MagicMock()
        cur.fetchone.return_value = {"cur_val": 90_000.0, "week_ago_val": float("nan")}
        with pytest.raises(ValueError, match="Invalid adjusted_equity"):
            _compute_weekly_loss(cur, __import__("datetime").date(2026, 8, 10))


class TestComputeSpyChangeRejectsNaN:
    def test_nan_latest_raises(self):
        cur = MagicMock()
        cur.fetchall.return_value = [{"close": float("nan")}, {"close": 500.0}]
        with pytest.raises(ValueError, match="Invalid SPY prices"):
            _compute_spy_change(cur, __import__("datetime").date(2026, 8, 10))

    def test_infinite_prior_raises(self):
        cur = MagicMock()
        cur.fetchall.return_value = [{"close": 505.0}, {"close": float("inf")}]
        with pytest.raises(ValueError, match="Invalid SPY prices"):
            _compute_spy_change(cur, __import__("datetime").date(2026, 8, 10))

    def test_valid_prices_still_compute(self):
        cur = MagicMock()
        cur.fetchall.return_value = [{"close": 505.0}, {"close": 500.0}]
        result = _compute_spy_change(cur, __import__("datetime").date(2026, 8, 10))
        assert result == pytest.approx(1.0)
