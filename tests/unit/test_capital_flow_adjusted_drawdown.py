"""Regression test for migration 1134's cash-flow-adjusted drawdown fix.

Locks in the exact incident this fixed: an external capital withdrawal must not be
read as a trading loss by the drawdown circuit breaker. See
migrations/versions/1134_add_capital_flow_adjusted_drawdown.sql for the full story.
"""

from unittest.mock import MagicMock

from algo.infrastructure.reconciliation import _compute_adjusted_drawdown


def test_withdrawal_does_not_inflate_drawdown() -> None:
    """A $20k withdrawal must be backed out of the peak, not counted as a loss."""
    cur = MagicMock()
    # First call: SUM(amount) of flows <= reconcile_date -> -20000 (one withdrawal recorded)
    # Second call: MAX(adjusted_equity) of prior snapshots -> prior peak was 100000
    cur.fetchone.side_effect = [(-20000.0,), (100000.0,)]

    portfolio_value = 80000.0  # raw equity dropped from 100k to 80k purely from the withdrawal
    net_flow, adjusted_peak, adjusted_dd = _compute_adjusted_drawdown(cur, "2026-01-01", portfolio_value)

    assert net_flow == -20000.0
    # adjusted_equity = 80000 - (-20000) = 100000 -> exactly matches pre-withdrawal peak
    assert adjusted_peak == 100000.0
    assert adjusted_dd == 0.0  # no real drawdown - the withdrawal was fully backed out


def test_real_trading_loss_still_shows_as_drawdown() -> None:
    """With no capital flows, a genuine equity decline must still register normally."""
    cur = MagicMock()
    cur.fetchone.side_effect = [(0.0,), (100000.0,)]

    portfolio_value = 85000.0  # genuine 15% trading loss, no withdrawals
    net_flow, adjusted_peak, adjusted_dd = _compute_adjusted_drawdown(cur, "2026-01-01", portfolio_value)

    assert net_flow == 0.0
    assert adjusted_peak == 100000.0
    assert adjusted_dd == 15.0
