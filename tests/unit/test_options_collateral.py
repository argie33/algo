"""Tests for algo/risk/options_collateral.py - phase 4 options-sleeve accounting.

Pure accounting logic against a mocked cursor, same style as
tests/unit/test_circuit_breaker_sector_drawdown.py.
"""

from decimal import Decimal
from unittest.mock import MagicMock

from algo.risk.options_collateral import (
    available_sleeve_capital,
    compute_committed_collateral,
    has_equity_overlap,
    sector_exposure_pct,
    underlying_exposure_pct,
)


def _cursor_with_fetchone(*values):
    """A MagicMock cursor whose fetchone() returns each of `values` in sequence, one per
    call - lets a test drive a function that issues multiple sequential queries."""
    cur = MagicMock()
    cur.fetchone.side_effect = list(values)
    return cur


def test_compute_committed_collateral_sums_open_rows():
    cur = _cursor_with_fetchone((Decimal("15000.00"),))
    result = compute_committed_collateral(cur)
    assert result == Decimal("15000.00")
    executed_sql = cur.execute.call_args[0][0]
    assert "status = 'open'" in executed_sql
    assert "SUM(collateral_amount)" in executed_sql


def test_compute_committed_collateral_empty_table_returns_zero():
    cur = _cursor_with_fetchone((0,))
    result = compute_committed_collateral(cur)
    assert result == Decimal("0")


def test_compute_committed_collateral_no_row_returns_zero():
    cur = _cursor_with_fetchone(None)
    result = compute_committed_collateral(cur)
    assert result == Decimal("0")


def test_available_sleeve_capital_subtracts_committed():
    # 5% of $200,000 equity = $10,000 sleeve cap; $3,000 already committed -> $7,000 free.
    cur = _cursor_with_fetchone((Decimal("3000"),))
    result = available_sleeve_capital(cur, Decimal("200000"))
    assert result == Decimal("7000")


def test_available_sleeve_capital_floors_at_zero_never_negative():
    # Committed collateral ($12,000) already exceeds the 5% sleeve cap ($10,000 on $200k
    # equity) - a real inconsistency circuit_breaker_options.py halts on separately, but
    # this pure accounting function must never return a negative "available" figure.
    cur = _cursor_with_fetchone((Decimal("12000"),))
    result = available_sleeve_capital(cur, Decimal("200000"))
    assert result == Decimal("0")


def test_underlying_exposure_pct_combines_open_collateral_and_assigned_cost_basis():
    # $2,000 open-CSP collateral + (cost_basis $48 * 100 assigned shares = $4,800) = $6,800
    # exposure on a $10,000 sleeve = 68%.
    cur = _cursor_with_fetchone((Decimal("2000"), Decimal("4800")))
    result = underlying_exposure_pct(cur, "AAPL", Decimal("10000"))
    assert result == Decimal("68")


def test_underlying_exposure_pct_no_exposure_is_zero():
    cur = _cursor_with_fetchone((0, 0))
    result = underlying_exposure_pct(cur, "AAPL", Decimal("10000"))
    assert result == Decimal("0")


def test_underlying_exposure_pct_zero_sleeve_capital_with_exposure_reports_full_breach():
    # Guards a divide-by-zero: any real exposure against a non-positive sleeve capital must
    # report as fully breaching (100%), never raise.
    cur = _cursor_with_fetchone((Decimal("100"), 0))
    result = underlying_exposure_pct(cur, "AAPL", Decimal("0"))
    assert result == Decimal("100")


def test_underlying_exposure_pct_zero_sleeve_capital_no_exposure_is_zero():
    cur = _cursor_with_fetchone((0, 0))
    result = underlying_exposure_pct(cur, "AAPL", Decimal("0"))
    assert result == Decimal("0")


def test_sector_exposure_pct_aggregates_across_symbols():
    cur = _cursor_with_fetchone((Decimal("1000"), Decimal("3000")))
    result = sector_exposure_pct(cur, "Technology", Decimal("10000"))
    assert result == Decimal("40")
    executed_sql = cur.execute.call_args[0][0]
    assert "WHERE sector = %s" in executed_sql


def test_has_equity_overlap_true_when_open_equity_position_exists():
    cur = MagicMock()
    cur.fetchone.side_effect = [(1,)]  # algo_positions hit - short-circuits before the 2nd query
    assert has_equity_overlap(cur, "AAPL") is True
    assert cur.execute.call_count == 1


def test_has_equity_overlap_true_when_open_sleeve_position_exists():
    cur = MagicMock()
    cur.fetchone.side_effect = [None, (1,)]  # no equity position, but an open sleeve row
    assert has_equity_overlap(cur, "AAPL") is True
    assert cur.execute.call_count == 2


def test_has_equity_overlap_false_when_neither_exists():
    cur = MagicMock()
    cur.fetchone.side_effect = [None, None]
    assert has_equity_overlap(cur, "AAPL") is False


def test_has_equity_overlap_checks_open_and_assigned_sleeve_statuses():
    cur = MagicMock()
    cur.fetchone.side_effect = [None, None]
    has_equity_overlap(cur, "AAPL")
    second_call_sql = cur.execute.call_args_list[1][0][0]
    assert "'open', 'assigned'" in second_call_sql
