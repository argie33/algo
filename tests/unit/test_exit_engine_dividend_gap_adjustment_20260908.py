#!/usr/bin/env python3
"""Test ExitEngine._dividend_gap_adjustment - the ex-dividend stop-loss false-trigger fix.

REAL-MONEY-READINESS FIX (2026-09-08 audit): a real ex-dividend gap-down (stock legitimately
opens lower by the dividend amount) previously read identically to an adverse price decline to
the stop-loss/target comparison in exit_engine.py, since only raw price_daily.close was ever
compared - price_daily.adj_close (populated independently by loaders/price_transformer.py) was
never consulted. These tests verify the divergence-detection math directly with concrete,
hand-computed numbers, not just that it runs without crashing.
"""

from datetime import date
from decimal import Decimal
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
        "use_scale_out_targets": True,
        "execution_mode": "paper",
        "alpaca_paper_trading": True,
    }


@pytest.fixture
def engine(mock_config):
    with patch("algo.trading.exit_engine.TradeExecutor"):
        yield ExitEngine(mock_config)


def _cursor_with_rows(rows):
    cur = MagicMock()
    cur.fetchall.return_value = rows
    return cur


def test_real_dividend_gap_detected_and_amount_correct(engine):
    # $50.00 prior close, $1.00/share dividend -> raw close drops to $49.00 (raw_return=-2%)
    # while adj_close stays smooth at $50.00 -> $49.50 (adj_return=-1%, reflecting only the
    # underlying 1% price move, not the mechanical dividend deduction).
    cur = _cursor_with_rows(
        [
            (date(2026, 9, 8), Decimal("49.00"), Decimal("49.50")),
            (date(2026, 9, 5), Decimal("50.00"), Decimal("50.00")),
        ]
    )
    adjustment = engine._dividend_gap_adjustment(cur, "TEST", date(2026, 9, 8))
    # implied_dividend = close_prev * (adj_return - raw_return) = 50 * (-0.01 - (-0.02)) = 0.50
    assert adjustment == pytest.approx(0.50, abs=1e-6)


def test_no_dividend_matching_returns_no_adjustment(engine):
    # Both series move identically (no corporate action) - divergence is exactly 0.
    cur = _cursor_with_rows(
        [
            (date(2026, 9, 8), Decimal("49.00"), Decimal("49.00")),
            (date(2026, 9, 5), Decimal("50.00"), Decimal("50.00")),
        ]
    )
    adjustment = engine._dividend_gap_adjustment(cur, "TEST", date(2026, 9, 8))
    assert adjustment == 0.0


def test_small_divergence_within_tolerance_ignored(engine):
    # A tiny (0.1%) divergence - noise, not a real corporate action - should not fire.
    cur = _cursor_with_rows(
        [
            (date(2026, 9, 8), Decimal("99.90"), Decimal("100.00")),
            (date(2026, 9, 5), Decimal("100.00"), Decimal("100.00")),
        ]
    )
    adjustment = engine._dividend_gap_adjustment(cur, "TEST", date(2026, 9, 8))
    assert adjustment == 0.0


def test_insufficient_history_returns_no_adjustment(engine):
    cur = _cursor_with_rows([(date(2026, 9, 8), Decimal("49.00"), Decimal("49.50"))])
    assert engine._dividend_gap_adjustment(cur, "TEST", date(2026, 9, 8)) == 0.0


def test_missing_adj_close_returns_no_adjustment(engine):
    cur = _cursor_with_rows(
        [
            (date(2026, 9, 8), Decimal("49.00"), None),
            (date(2026, 9, 5), Decimal("50.00"), Decimal("50.00")),
        ]
    )
    assert engine._dividend_gap_adjustment(cur, "TEST", date(2026, 9, 8)) == 0.0


def test_unexpected_row_shape_is_a_safe_noop(engine):
    # Defensive guard for a shared test-double fixture returning a differently-shaped row
    # than this method's own SELECT would ever produce against a real DB - never a crash.
    cur = _cursor_with_rows([(date(2026, 9, 8), Decimal("49.00")), (date(2026, 9, 5), Decimal("50.00"))])
    assert engine._dividend_gap_adjustment(cur, "TEST", date(2026, 9, 8)) == 0.0


def test_real_gap_would_have_prevented_false_stop_trigger(engine):
    """End-to-end sanity: a stop at $49.20 would incorrectly trigger against the raw $49.00
    close on an ex-div day, but should NOT trigger once the dividend gap is added back."""
    cur = _cursor_with_rows(
        [
            (date(2026, 9, 8), Decimal("49.00"), Decimal("49.50")),
            (date(2026, 9, 5), Decimal("50.00"), Decimal("50.00")),
        ]
    )
    raw_close = 49.00
    stop_level = 49.20
    assert raw_close <= stop_level  # would falsely trigger on raw close alone

    adjusted_price = raw_close + engine._dividend_gap_adjustment(cur, "TEST", date(2026, 9, 8))
    assert adjusted_price == pytest.approx(49.50, abs=1e-6)
    assert adjusted_price > stop_level  # correctly does not trigger once dividend-adjusted
