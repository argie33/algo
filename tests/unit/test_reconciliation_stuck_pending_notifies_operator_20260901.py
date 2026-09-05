"""Regression test: DailyReconciliation.check_pending_reconciliations() must actually
notify an operator when a trade's estimated exit price has been stuck (>1 day) without
Alpaca fill-price reconciliation, not just log a critical line.

Before this fix, a stuck reconciliation only ever reached logger.critical() - unlike
every other CRITICAL condition in this same file (broker cash missing/negative, account
fetch failure, portfolio_value missing), which all call notify(). Effect: P&L/portfolio
value/drawdown get silently computed off a stale ESTIMATED exit price indefinitely, with
no operator ever notified. Same "computed but never delivered" bug class already found
and fixed for Phase 9's VaR/concentration/beta alerts (commit 5ac092eea).

Follows the established mock pattern from test_reconciliation_partial_fill_correction.py:
execution_mode != "auto" short-circuits __init__ before it needs live broker credentials.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from algo.infrastructure.reconciliation import DailyReconciliation


def _reconciliation() -> DailyReconciliation:
    return DailyReconciliation({"execution_mode": "paper"})


def test_stuck_reconciliation_notifies_operator():
    reconciliation = _reconciliation()
    cur = MagicMock()
    stuck_exit_date = (datetime.now(timezone.utc) - timedelta(days=3)).date()
    cur.fetchall.return_value = [
        ("trade-999", "ZZZZ", stuck_exit_date, 10.0, 9.5, None, None),
    ]

    with patch("algo.infrastructure.reconciliation_exit_fills.notify") as mock_notify:
        result = reconciliation.check_pending_reconciliations(cur)

    assert result["stuck_count"] == 1
    mock_notify.assert_called_once()
    assert mock_notify.call_args.args[0] == "critical"
    message = mock_notify.call_args.kwargs.get("message", "")
    assert "ZZZZ" in message
    assert "trade-999" in message


def test_not_yet_stuck_pending_reconciliation_does_not_notify():
    """A pending reconciliation still within the 1-day grace window must not alert -
    only genuinely stuck (>1 day) ones should."""
    reconciliation = _reconciliation()
    cur = MagicMock()
    fresh_exit_date = datetime.now(timezone.utc).date()
    cur.fetchall.return_value = [
        ("trade-1", "AAPL", fresh_exit_date, 10.0, 9.5, None, None),
    ]

    with patch("algo.infrastructure.reconciliation_exit_fills.notify") as mock_notify:
        result = reconciliation.check_pending_reconciliations(cur)

    assert result["stuck_count"] == 0
    mock_notify.assert_not_called()
