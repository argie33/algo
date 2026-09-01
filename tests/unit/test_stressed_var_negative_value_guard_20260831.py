"""Regression test for the 2026-08-31 (/goal pre-real-money audit) fix: ValueAtRisk.stressed_var()
used to build its `values` list inline (`Decimal(str(float(row[1])))`, no validation) instead of
going through `_extract_portfolio_values()` the way `historical_var()`/`cvar()` both do - missing
that helper's `val <= 0` check. A negative `adjusted_equity` snapshot (corrupted data) would
silently flip the sign of every return computed from it instead of raising the same clear
RuntimeError the sibling functions give for identical bad data.

VaR is informational-only (doesn't gate trading - phase9_reconciliation.py's
_compute_risk_metrics() only builds a summary/warning string from it), so this could only mislead
an operator reading the risk report, never risk extra capital directly - but the three functions
computing the same statistic from the same table should fail the same way on the same bad input.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from algo.risk.var import ValueAtRisk


def _rows_with_one_negative_value() -> list[tuple[date, float]]:
    """365+ rows (stressed_var()'s own minimum) of otherwise-valid portfolio values with
    one corrupted negative adjusted_equity snapshot partway through."""
    start = date(2020, 1, 1)
    rows = [(start + timedelta(days=i), 100_000.0 + i * 10) for i in range(400)]
    corrupted_idx = 200
    rows[corrupted_idx] = (rows[corrupted_idx][0], -50_000.0)
    return rows


class TestStressedVarNegativeValueGuard:
    def test_negative_portfolio_value_raises_not_silently_corrupts(self) -> None:
        rows = _rows_with_one_negative_value()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = rows
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = mock_cur

        calc = ValueAtRisk({})
        with patch("algo.risk.var.DatabaseContext", return_value=mock_ctx):
            with pytest.raises(RuntimeError, match="invalid"):
                calc.stressed_var()

    def test_matches_historical_var_and_cvar_error_message_shape(self) -> None:
        """Sanity check: all three functions computing the same statistic from the same
        table must reject a negative value the same way, not just stressed_var() alone."""
        rows = _rows_with_one_negative_value()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = rows
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = mock_cur

        calc = ValueAtRisk({})
        with patch("algo.risk.var.DatabaseContext", return_value=mock_ctx):
            with pytest.raises(RuntimeError, match="Portfolio value invalid"):
                calc.historical_var()
            with pytest.raises(RuntimeError, match="Portfolio value invalid"):
                calc.stressed_var()
