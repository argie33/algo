#!/usr/bin/env python3
"""Regression test for a 2026-08-31 gap: PositionSizer._fetch_live_alpaca_equity() accepted
any HTTP 200 /v2/account response at face value - a degraded-but-200-OK broker response
(stale cache, wrong account payload, a decimal-place shift on Alpaca's side) has no HTTP
error or exception to catch it, and would have flowed straight into position sizing as if it
were real. Fixed by adding PositionSizer._validate_alpaca_equity(): rejects non-numeric,
non-positive, NaN/infinite values outright, and rejects any value outside
[MIN_RATIO, MAX_RATIO] of the last known portfolio snapshot as an implausible single-fetch
move (see ALPACA_EQUITY_MIN/MAX_RATIO_VS_LAST_SNAPSHOT and circuit_breaker.py's own 20%
portfolio-drawdown halt - trading should already be stopped long before a real loss/gain gets
anywhere near this floor/ceiling).
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from algo.trading.position_sizer import PositionSizer

CONFIG = {
    "base_risk_pct": 1.0,
    "max_positions": 15,
    "min_risk_pct_floor": 0.5,
    "max_position_size_pct": 10.0,
    "max_concentration_pct": 15.0,
    "max_total_invested_pct": 90.0,
    "max_total_risk_pct": 4.0,
    "risk_reduction_at_minus_5": 0.75,
    "risk_reduction_at_minus_10": 0.5,
    "risk_reduction_at_minus_15": 0.25,
    "risk_reduction_at_minus_20": 0.0,
    "vix_caution_threshold": 25.0,
    "vix_max_threshold": 35.0,
    "vix_caution_risk_reduction": 0.5,
}


def _make_sizer():
    return PositionSizer(config=dict(CONFIG))


def test_rejects_zero_equity():
    sizer = _make_sizer()
    with patch.object(sizer, "_last_known_portfolio_snapshot_value", return_value=None):
        with pytest.raises(RuntimeError, match="implausible portfolio value"):
            sizer._validate_alpaca_equity("0")


def test_rejects_negative_equity():
    sizer = _make_sizer()
    with patch.object(sizer, "_last_known_portfolio_snapshot_value", return_value=None):
        with pytest.raises(RuntimeError, match="implausible portfolio value"):
            sizer._validate_alpaca_equity("-500.00")


def test_rejects_nan_equity():
    sizer = _make_sizer()
    with patch.object(sizer, "_last_known_portfolio_snapshot_value", return_value=None):
        with pytest.raises(RuntimeError, match="implausible portfolio value"):
            sizer._validate_alpaca_equity("NaN")


def test_rejects_non_numeric_equity():
    sizer = _make_sizer()
    with patch.object(sizer, "_last_known_portfolio_snapshot_value", return_value=None):
        with pytest.raises(RuntimeError, match="non-numeric portfolio value"):
            sizer._validate_alpaca_equity("null")


def test_accepts_plausible_value_with_no_prior_snapshot():
    """First-ever run: nothing to compare against, only the absolute checks apply."""
    sizer = _make_sizer()
    with patch.object(sizer, "_last_known_portfolio_snapshot_value", return_value=None):
        assert sizer._validate_alpaca_equity("100000.00") == Decimal("100000.00")


def test_accepts_normal_daily_move():
    sizer = _make_sizer()
    with patch.object(sizer, "_last_known_portfolio_snapshot_value", return_value=Decimal("100000")):
        # A real, if unusually large, up day - well within the plausible band.
        assert sizer._validate_alpaca_equity("115000.00") == Decimal("115000.00")


def test_rejects_broker_response_far_below_last_snapshot():
    """Simulates a degraded Alpaca response reporting near-zero equity for a funded account."""
    sizer = _make_sizer()
    with patch.object(sizer, "_last_known_portfolio_snapshot_value", return_value=Decimal("100000")):
        with pytest.raises(RuntimeError, match="degraded broker response"):
            sizer._validate_alpaca_equity("500.00")


def test_rejects_broker_response_far_above_last_snapshot():
    """Simulates Alpaca returning another (much larger) account's balance."""
    sizer = _make_sizer()
    with patch.object(sizer, "_last_known_portfolio_snapshot_value", return_value=Decimal("100000")):
        with pytest.raises(RuntimeError, match="degraded broker response"):
            sizer._validate_alpaca_equity("5000000.00")


def test_snapshot_lookup_failure_does_not_block_a_plausible_value():
    """The sanity-check comparison is best-effort - a DB hiccup fetching the last snapshot
    must not itself fail closed on an otherwise-valid equity value."""
    sizer = _make_sizer()
    with patch.object(sizer, "_with_cursor", side_effect=RuntimeError("db down")):
        assert sizer._validate_alpaca_equity("100000.00") == Decimal("100000.00")
