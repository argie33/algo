"""Regression test: AlpacaSyncManager._sync_untracked_positions must alert an operator when
a genuinely new untracked broker position is detected.

An untracked position means a real broker position (real shares, real dollars) with no
matching algo_trades/algo_positions row - no stop-loss, no exit management, and no
risk-limit accounting will ever apply to it, since every other part of this system assumes
a position it doesn't know about doesn't exist. Before this fix, detection only wrote a row
to algo_untracked_positions - a table dashboard/panels/health.py explicitly excludes from
its staleness alarms and never checks the row count of either - so a real orphaned position
could sit silently for days with nothing surfacing it to a human. Live orchestrator risk
review (2026-07-27) traced this gap starting from phase8_entry_execution.py's documented
duplicate-check race condition (a broker fill can succeed while the DB insert fails).
"""

from unittest.mock import MagicMock, patch

from algo.infrastructure.alpaca_sync_manager import AlpacaSyncManager


def _make_manager():
    return object.__new__(AlpacaSyncManager)


def test_newly_detected_untracked_position_sends_critical_alert():
    manager = _make_manager()
    cur = MagicMock()
    cur.fetchone.return_value = None  # no existing row -> INSERT branch
    cur.rowcount = 1

    with patch("algo.reporting.notifications.notify") as mock_notify:
        manager._sync_untracked_positions(
            cur,
            orphan_symbols=["AAPL"],
            alpaca_positions=[{"symbol": "AAPL", "qty": "10", "current_price": "200.00"}],
        )

    mock_notify.assert_called_once()
    args, kwargs = mock_notify.call_args
    assert args[0] == "critical" or kwargs.get("severity") == "critical"
    call_str = str(args) + str(kwargs)
    assert "AAPL" in call_str


def test_already_known_untracked_position_does_not_realert():
    manager = _make_manager()
    cur = MagicMock()
    cur.fetchone.return_value = (1,)  # existing row -> UPDATE branch, not new
    cur.rowcount = 1

    with patch("algo.reporting.notifications.notify") as mock_notify:
        manager._sync_untracked_positions(
            cur,
            orphan_symbols=["AAPL"],
            alpaca_positions=[{"symbol": "AAPL", "qty": "10", "current_price": "200.00"}],
        )

    mock_notify.assert_not_called()


def test_notification_failure_fails_fast():
    """Untracked position alerts MUST fail-fast if notification fails.

    Silent notification failures mean operators never learn about untracked broker positions
    (real shares, real dollars with no risk management). This violates fail-fast principle.
    If we can't alert operators, reconciliation must halt for manual review.
    """
    manager = _make_manager()
    cur = MagicMock()
    cur.fetchone.return_value = None
    cur.rowcount = 1

    with patch("algo.reporting.notifications.notify", side_effect=RuntimeError("smtp down")):
        # Must raise when notification fails - operators must be aware of untracked positions
        try:
            manager._sync_untracked_positions(
                cur,
                orphan_symbols=["AAPL"],
                alpaca_positions=[{"symbol": "AAPL", "qty": "10", "current_price": "200.00"}],
            )
            raise AssertionError("Should have raised RuntimeError on notification failure")
        except RuntimeError as e:
            assert "untracked-position alert" in str(e).lower() or "notify" in str(e).lower()
