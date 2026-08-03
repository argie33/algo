"""Tests for CircuitBreaker._check_sector_drawdown.

sector_drawdown_halt_pct has been a seeded, validated, admin-editable algo_config value
since migration 005 - documented in
algo/infrastructure/config/circuit_breaker_config.py's own module docstring as one of
this codebase's 8 core circuit-breaker categories - but nothing ever read it to actually
halt trading. This is the first real implementation, wired into
CircuitBreaker._check_registry as CB9.
"""

from datetime import date
from unittest.mock import MagicMock

import pytest

from algo.risk.circuit_breaker import CircuitBreaker


def _make_cursor(position_rows, sector_drawdown_halt_pct="-12.0"):
    cur = MagicMock()
    cur.fetchall.return_value = position_rows
    return cur


@pytest.fixture
def cb():
    return CircuitBreaker(config={"sector_drawdown_halt_pct": "-12.0"})


def test_no_open_positions_not_halted(cb):
    cur = _make_cursor([])
    result = cb._check_sector_drawdown(date(2026, 7, 26), cur)
    assert result["halted"] is False
    assert result["reason"] == "No open positions"


def test_sector_within_threshold_not_halted(cb):
    # Tech sector: $10,000 basis, -$500 unrealized = -5% (above -12% threshold)
    rows = [
        ("Technology", -500.0, 100.0, 100),
    ]
    cur = _make_cursor(rows)
    result = cb._check_sector_drawdown(date(2026, 7, 26), cur)
    assert result["halted"] is False
    assert result["value"] == -5.0
    assert result["sector"] == "Technology"


def test_sector_breaching_threshold_halts(cb):
    # Tech sector: $10,000 basis, -$1500 unrealized = -15% (breaches -12% threshold)
    rows = [
        ("Technology", -1500.0, 100.0, 100),
    ]
    cur = _make_cursor(rows)
    result = cb._check_sector_drawdown(date(2026, 7, 26), cur)
    assert result["halted"] is True
    assert result["value"] == -15.0
    assert result["threshold"] == -12.0


def test_weighted_by_cost_basis_not_simple_average(cb):
    """A large losing position must outweigh a small winning one in the same sector -
    a naive average of unrealized_pnl_pct per-position would get this wrong."""
    rows = [
        # Small winning position: $500 basis, +$50 (=+10%)
        ("Technology", 50.0, 50.0, 10),
        # Large losing position: $50,000 basis, -$7500 (=-15%)
        ("Technology", -7500.0, 500.0, 100),
    ]
    cur = _make_cursor(rows)
    result = cb._check_sector_drawdown(date(2026, 7, 26), cur)
    # Weighted: (50 - 7500) / (500 + 50000) * 100 = -14.75%, well past -12% threshold.
    # A naive average of (+10%, -15%) = -2.5% would have missed this entirely.
    assert result["halted"] is True
    assert result["value"] == pytest.approx(-14.75, abs=0.01)


def test_worst_sector_selected_across_multiple_sectors(cb):
    rows = [
        ("Technology", -200.0, 100.0, 100),  # -2%
        ("Healthcare", -1800.0, 100.0, 100),  # -18%, worst
        ("Energy", 500.0, 100.0, 100),  # +5%
    ]
    cur = _make_cursor(rows)
    result = cb._check_sector_drawdown(date(2026, 7, 26), cur)
    assert result["sector"] == "Healthcare"
    assert result["halted"] is True


def test_missing_sector_gracefully_skips_position(cb):
    """Missing sector (NULL from LEFT JOIN) should skip position, not halt orchestrator."""
    rows = [(None, -500.0, 100.0, 100)]
    cur = _make_cursor(rows)
    result = cb._check_sector_drawdown(date(2026, 7, 26), cur)
    # Should not halt - insufficient data but that's degradation, not a halt
    assert result["halted"] is False
    assert "Insufficient data" in result.get("reason", "")


def test_missing_pnl_data_gracefully_skips_position(cb):
    """Missing P&L data should skip position, not halt orchestrator."""
    rows = [("Technology", None, 100.0, 100)]
    cur = _make_cursor(rows)
    result = cb._check_sector_drawdown(date(2026, 7, 26), cur)
    # Should not halt - position re-syncs in Phase 3, orchestrator continues
    assert result["halted"] is False
    assert "Insufficient data" in result.get("reason", "")


def test_missing_config_key_raises():
    cb = CircuitBreaker(config={})
    rows = [("Technology", -500.0, 100.0, 100)]
    cur = _make_cursor(rows)
    with pytest.raises(ValueError, match="sector_drawdown_halt_pct"):
        cb._check_sector_drawdown(date(2026, 7, 26), cur)


def test_positive_threshold_misconfiguration_fails_closed_halted():
    """sector_drawdown_halt_pct must be negative (same convention as
    halt_drawdown_pct/max_daily_loss_pct/max_weekly_loss_pct) - a positive value is a
    misconfiguration that must halt, not silently compare backwards."""
    cb = CircuitBreaker(config={"sector_drawdown_halt_pct": "12.0"})
    rows = [("Technology", -500.0, 100.0, 100)]
    cur = _make_cursor(rows)
    result = cb._check_sector_drawdown(date(2026, 7, 26), cur)
    assert result["halted"] is True
    assert "misconfigured" in result["reason"]


def test_sector_drawdown_registered_in_check_registry():
    cb = CircuitBreaker(config={})
    assert "sector_drawdown" in cb._check_registry
    assert "sector_drawdown" in cb._checks
    assert cb._checks["sector_drawdown"] == cb._check_sector_drawdown
