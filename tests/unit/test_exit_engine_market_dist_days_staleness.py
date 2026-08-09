#!/usr/bin/env python3
"""Regression test: ExitEngine._fetch_market_dist_days must hard-gate on stale
market_exposure_daily data, not silently reuse an arbitrarily old row.

Phase 1 treats market_exposure_daily staleness as a WARNING only (see
utils/validation/freshness_config.py + phase1_data_freshness.py's own docstring
listing it under "WARNING IF STALE"), so it never halts the orchestrator. Before
this fix, _fetch_market_dist_days's fallback query ("most recent non-NULL row on
or before current_date") had no staleness bound at all - if the market_exposure_daily
EOD loader stalled for days, exit_engine would keep computing real risk decisions
(the >max_distribution_days de-risking check) off a stale distribution-day count
with nothing in the pipeline ever halting or even warning about it. This is a real
gap for a system about to trade real money: a silently stuck loader should never be
indistinguishable from "market is calm" at the exit-risk layer.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from algo.trading.exit_engine import ExitEngine


@pytest.fixture
def mock_config():
    return {
        "min_hold_days": 1,
        "max_hold_days": 60,
        "eight_week_rule_threshold_pct": 20.0,
        "eight_week_rule_window_days": 21,
        "exit_on_distribution_day": False,
        "max_distribution_days": 3,
        "move_be_at_r": 1.0,
        "chandelier_atr_mult": 3.0,
        "use_chandelier_trail": False,
        "exit_on_td_sequential": False,
        "exit_on_rs_line_break_50dma": False,
        "require_target_pullback": True,
        "execution_mode": "paper",
        "alpaca_paper_trading": True,
    }


def _engine(mock_config):
    with patch("algo.trading.exit_engine.TradeExecutor"):
        return ExitEngine(mock_config)


def test_one_trading_day_lag_is_normal_and_does_not_raise(mock_config):
    """Morning runs normally see the prior trading day's EOD-computed row - this
    single-day lag is expected behavior, not staleness, and must not raise."""
    current_date = date(2026, 8, 11)  # Tuesday
    row_date = date(2026, 8, 10)  # Monday - previous trading day, 1 day lag

    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = (8, False, None, row_date)

    engine = _engine(mock_config)
    result = engine._fetch_market_dist_days(mock_cur, current_date)

    assert result == 8


def test_multi_day_stale_row_raises_instead_of_silently_reusing(mock_config):
    """A market_exposure_daily row that's many trading days old (loader stalled,
    not just lagging) must hard-fail exit evaluation instead of silently feeding
    a stale distribution-day count into de-risking decisions."""
    current_date = date(2026, 8, 11)  # Tuesday
    row_date = date(2026, 8, 3)  # Monday, previous week - loader stuck for days

    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = (8, False, None, row_date)

    engine = _engine(mock_config)

    with pytest.raises(RuntimeError, match="MARKET_DIST_DAYS_STALE"):
        engine._fetch_market_dist_days(mock_cur, current_date)


def test_same_day_row_does_not_raise(mock_config):
    """EOD/afternoon runs see the same-day recomputed row - zero lag, must not raise."""
    current_date = date(2026, 8, 11)

    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = (5, False, None, current_date)

    engine = _engine(mock_config)
    result = engine._fetch_market_dist_days(mock_cur, current_date)

    assert result == 5


def test_no_row_still_raises_missing_not_stale(mock_config):
    """Existing behavior (no matching row at all) must be preserved unchanged."""
    current_date = date(2026, 8, 11)

    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = None

    engine = _engine(mock_config)

    with pytest.raises(RuntimeError, match="MARKET_DIST_DAYS_MISSING"):
        engine._fetch_market_dist_days(mock_cur, current_date)
