"""Regression tests for _vol_managed_multiplier(), activated 2026-08-24 after a Phase B
backtest (see the method's own docstring for methodology/results) replaced its prior
PINNED-TO-1.0 stub with a real Moreira & Muir (2017) vol-managed scaling computation:
weight = target_vol (full-sample annualized stdev) / realized_vol (trailing 21-trading-day
annualized stdev), capped to [0.25, 2.0].

The stub's only behavior worth testing was "always returns 1.0" (covered incidentally by
every other market_exposure test that never triggers a real computation). These tests cover
the real computation added in its place: graceful degradation to neutral 1.0 on missing/
insufficient data or a DB error, and correct cap enforcement in both directions.
"""

import math
from datetime import date
from unittest.mock import MagicMock

import psycopg2
import pytest

from algo.risk.market_exposure import MarketExposure

EVAL_DATE = date(2026, 8, 24)


def _closes_desc_rows(returns: list[float], start: float = 100.0) -> list[tuple[float]]:
    """Build DESC-ordered (close,) rows matching the real query's row shape, from a list of
    daily returns applied oldest-first to a starting price.
    """
    closes = [start]
    for r in returns:
        closes.append(closes[-1] * (1 + r))
    return [(c,) for c in reversed(closes)]


class TestGracefulDegradation:
    def test_insufficient_history_returns_neutral(self) -> None:
        cur = MagicMock()
        cur.fetchall.return_value = _closes_desc_rows([0.001] * 100)  # well under 252 min
        me = MarketExposure()
        assert me._vol_managed_multiplier(EVAL_DATE, cur) == 1.0

    def test_db_error_returns_neutral(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = psycopg2.OperationalError("connection lost")
        me = MarketExposure()
        assert me._vol_managed_multiplier(EVAL_DATE, cur) == 1.0

    def test_zero_realized_vol_returns_neutral(self) -> None:
        # All-identical prices after the initial move -> last-21-day realized_vol == 0,
        # would otherwise divide by zero.
        cur = MagicMock()
        returns = [0.001] * 300 + [0.0] * 21
        cur.fetchall.return_value = _closes_desc_rows(returns)
        me = MarketExposure()
        result = me._vol_managed_multiplier(EVAL_DATE, cur)
        assert result == 1.0


class TestCapEnforcement:
    def test_high_recent_vol_relative_to_history_clips_to_lower_cap(self) -> None:
        # Long quiet history (small alternating returns) + a violently choppy last month ->
        # realized_vol >> target_vol -> weight clipped to the 0.25 floor.
        cur = MagicMock()
        base = [0.001, -0.001] * 190  # 380 quiet days
        recent = [0.05, -0.05] * 11  # 22 days, last 21 dominate the realized window
        cur.fetchall.return_value = _closes_desc_rows(base + recent)
        me = MarketExposure()
        result = me._vol_managed_multiplier(EVAL_DATE, cur)
        assert result == pytest.approx(0.25)

    def test_low_recent_vol_relative_to_history_clips_to_upper_cap(self) -> None:
        # Long choppy history + a suddenly dead-calm last month -> realized_vol << target_vol
        # -> weight clipped to the 2.0 ceiling.
        cur = MagicMock()
        base = [0.05, -0.05] * 190  # 380 volatile days
        recent = [0.001, -0.001] * 11
        cur.fetchall.return_value = _closes_desc_rows(base + recent)
        me = MarketExposure()
        result = me._vol_managed_multiplier(EVAL_DATE, cur)
        assert result == pytest.approx(2.0)

    def test_result_always_within_cap_bounds(self) -> None:
        cur = MagicMock()
        # Moderate, uniform vol throughout - shouldn't need clipping, but assert the
        # invariant directly rather than a fragile exact value.
        returns = [0.01, -0.008, 0.005, -0.012, 0.003] * 80
        cur.fetchall.return_value = _closes_desc_rows(returns)
        me = MarketExposure()
        result = me._vol_managed_multiplier(EVAL_DATE, cur)
        assert 0.25 <= result <= 2.0
        assert not math.isnan(result)
        assert not math.isinf(result)


class TestNonFiniteGuards:
    def test_nan_close_in_window_is_skipped_not_crashed(self) -> None:
        cur = MagicMock()
        rows = _closes_desc_rows([0.001] * 300)
        # Corrupt one row's close with NaN - must not raise or poison the computation.
        rows[5] = (float("nan"),)
        cur.fetchall.return_value = rows
        me = MarketExposure()
        result = me._vol_managed_multiplier(EVAL_DATE, cur)
        assert not math.isnan(result)
        assert 0.25 <= result <= 2.0

    def test_non_positive_close_is_skipped_not_crashed(self) -> None:
        cur = MagicMock()
        rows = _closes_desc_rows([0.001] * 300)
        rows[5] = (0.0,)
        cur.fetchall.return_value = rows
        me = MarketExposure()
        result = me._vol_managed_multiplier(EVAL_DATE, cur)
        assert not math.isnan(result)
        assert 0.25 <= result <= 2.0
