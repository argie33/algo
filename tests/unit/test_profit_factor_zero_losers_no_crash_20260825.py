"""Regression test: ReconciliationAnalytics.compute_closed_trade_metrics() used to raise
ValueError whenever gross_loss <= 0 (zero losing closed trades, or all losing trades landed
at exactly breakeven) - treating a genuinely benign account state (e.g. the first few trades
of a live account all being winners) as a "data quality issue". That exception propagated
all the way up through DailyReconciliation.run_daily_reconciliation()'s outer except clause,
turning a good trading outcome into a reported reconciliation FAILURE for the entire day -
not just a missing profit_factor field.

profit_factor is mathematically undefined (division by zero) when gross_loss==0 - the fix
reports it as None (matching how avg_r_multiple/best_trade_pct/etc. already report
"unavailable" in this same function, and how downstream dashboard consumers already read
profit_factor via safe_float(..., default=None, allow_none=True)) instead of raising.

Fixed 2026-08-25 (money-% goal-session audit).
"""

from unittest.mock import MagicMock

from algo.infrastructure.reconciliation_analytics import ReconciliationAnalytics


def _mock_cursor(wins: int, losses: int, gross_profit: float, gross_loss: float) -> MagicMock:
    cur = MagicMock()
    cur.fetchone.return_value = (
        wins,
        losses,
        gross_profit,
        gross_loss,
        1.5,  # avg_r_multiple
        12.0,  # best_trade_pct
        -3.0,  # worst_trade_pct
        -2.0,  # avg_mae
        8.0,  # avg_mfe
        wins + losses,  # total_closed
    )
    return cur


def test_zero_losing_trades_does_not_raise() -> None:
    """3 winning trades, 0 losers (e.g. week 1 of a live account) - gross_loss is exactly
    0.0. Must return profit_factor=None, not raise."""
    analytics = ReconciliationAnalytics()
    cur = _mock_cursor(wins=3, losses=0, gross_profit=450.0, gross_loss=0.0)

    result = analytics.compute_closed_trade_metrics(cur)

    assert result["profit_factor"] is None
    assert result["win_count"] == 3
    assert result["loss_count"] == 0
    assert "undefined" in result["reason"]
    assert "3W 0L" in result["reason"]


def test_all_breakeven_losses_does_not_raise() -> None:
    """2 wins, 2 losses that both landed at exactly $0.00 P&L - gross_loss sums to 0.0
    even though loss_count > 0. Must still return profit_factor=None, not raise."""
    analytics = ReconciliationAnalytics()
    cur = _mock_cursor(wins=2, losses=2, gross_profit=300.0, gross_loss=0.0)

    result = analytics.compute_closed_trade_metrics(cur)

    assert result["profit_factor"] is None
    assert result["loss_count"] == 2


def test_normal_case_still_computes_profit_factor() -> None:
    """Sanity check: a real mix of wins and losses still computes the ordinary ratio."""
    analytics = ReconciliationAnalytics()
    cur = _mock_cursor(wins=6, losses=4, gross_profit=1200.0, gross_loss=400.0)

    result = analytics.compute_closed_trade_metrics(cur)

    assert result["profit_factor"] == 3.0
    assert "3.00x" in result["reason"]
