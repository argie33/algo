"""Regression tests for the 2026-08-21 fix (finance-accuracy audit): loaders/
compute_circuit_breakers.py never computed sector drawdown, despite algo/risk/
circuit_breaker.py's real halt gate enforcing it since commit f20b6e42a - an operator
watching circuit_breaker_status/the dashboard had no way to see WHY a sector-drawdown
halt fired. See migration 1215.

_compute_sector_drawdown must mirror algo/risk/circuit_breaker.py::_check_sector_drawdown's
exact weighting (cost-basis-weighted, not a simple average) and NaN/Inf guards, so this
reporting value can never diverge from what the real gate is actually evaluating.
"""

from unittest.mock import MagicMock

from loaders.compute_circuit_breakers import _compute_sector_drawdown


def _rows(*rows):
    cur = MagicMock()
    cur.fetchall.return_value = [
        {"sector": s, "unrealized_pnl": pnl, "entry_price": ep, "quantity": qty} for s, pnl, ep, qty in rows
    ]
    return cur


class TestComputeSectorDrawdown:
    def test_no_open_positions_returns_zero_no_sector(self):
        cur = _rows()
        pct, sector = _compute_sector_drawdown(cur)
        assert pct == 0.0
        assert sector is None

    def test_cost_basis_weighted_not_simple_average(self):
        """A $500 losing position and a $50,000 winning position in the same sector must
        be weighted by dollars, not averaged as if equally sized."""
        cur = _rows(
            ("Tech", -250.0, 50.0, 10),  # $500 basis, -50% return
            ("Tech", 5000.0, 100.0, 500),  # $50,000 basis, +10% return
        )
        pct, sector = _compute_sector_drawdown(cur)
        # Weighted: (-250 + 5000) / (500 + 50000) * 100 = 9.41%, NOT the simple
        # average of -50% and +10% (-20%).
        assert sector == "Tech"
        assert 9.0 < pct < 9.5

    def test_worst_sector_selected_across_multiple_sectors(self):
        cur = _rows(
            ("Tech", 1000.0, 100.0, 100),  # +10%
            ("Energy", -3000.0, 100.0, 100),  # -30%
        )
        pct, sector = _compute_sector_drawdown(cur)
        assert sector == "Energy"
        assert pct == -30.0

    def test_missing_sector_skipped(self):
        cur = _rows((None, -1000.0, 100.0, 100))
        pct, sector = _compute_sector_drawdown(cur)
        assert pct == 0.0
        assert sector is None

    def test_missing_pnl_data_skipped(self):
        cur = _rows(("Tech", None, 100.0, 100))
        pct, sector = _compute_sector_drawdown(cur)
        assert pct == 0.0
        assert sector is None

    def test_nan_cost_basis_skipped_not_propagated(self):
        """Same NaN-comparison-guard class fixed elsewhere in this file (2026-08-10):
        `cost_basis <= 0` never catches NaN, so an explicit isnan() check is required."""
        cur = _rows(("Tech", float("nan"), 100.0, 100))
        pct, sector = _compute_sector_drawdown(cur)
        assert pct == 0.0
        assert sector is None

    def test_zero_cost_basis_skipped(self):
        cur = _rows(("Tech", -100.0, 0.0, 100))
        pct, sector = _compute_sector_drawdown(cur)
        assert pct == 0.0
        assert sector is None
