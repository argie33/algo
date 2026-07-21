"""Verifies DailyReconciliation.check_partial_fills() actually corrects DB quantity
drift against the broker (source of truth), rather than trusting whatever the DB
already believes was filled.

Replaces tests/test_session_281_critical_fixes.py::test_reconciliation_must_handle_partial_fills,
which was left as an unconditional pytest.skip() marked "AUDIT TODO (Session 282)"
for two sessions - it never actually verified the 100-requested/60-filled scenario
its own docstring described.
"""

from unittest.mock import MagicMock, patch

from algo.infrastructure.reconciliation import DailyReconciliation


def _reconciliation_with_mock_broker() -> DailyReconciliation:
    # execution_mode != "auto" short-circuits __init__ before it tries to build a real
    # AlpacaBrokerAdapter (which needs live credentials) - self.broker is then replaced
    # with a mock, matching how check_partial_fills only cares about self.broker's interface.
    reconciliation = DailyReconciliation({"execution_mode": "paper"})
    reconciliation.broker = MagicMock()
    return reconciliation


def test_partial_fill_corrects_db_quantity_to_match_broker():
    """100 requested, broker only filled 60 -> DB must be corrected to 60, not left at 100."""
    reconciliation = _reconciliation_with_mock_broker()
    reconciliation.broker.fetch_closed_orders.return_value = [
        {"symbol": "AAPL", "filled_qty": "60", "status": "partially_filled"}
    ]
    cur = MagicMock()
    cur.fetchone.return_value = ("trade-123", 100, "open")

    with patch("algo.infrastructure.reconciliation.notify"):
        result = reconciliation.check_partial_fills(cur)

    assert result["mismatches"] == 1
    assert result["details"][0]["db_quantity"] == 100
    assert result["details"][0]["alpaca_filled"] == 60

    update_calls = [c for c in cur.execute.call_args_list if "UPDATE algo_trades" in c.args[0]]
    assert len(update_calls) == 1
    assert update_calls[0].args[1] == (60, "trade-123")


def test_partial_fill_notifies_operator_of_correction():
    reconciliation = _reconciliation_with_mock_broker()
    reconciliation.broker.fetch_closed_orders.return_value = [
        {"symbol": "AAPL", "filled_qty": "60", "status": "partially_filled"}
    ]
    cur = MagicMock()
    cur.fetchone.return_value = ("trade-123", 100, "open")

    with patch("algo.infrastructure.reconciliation.notify") as mock_notify:
        reconciliation.check_partial_fills(cur)

    mock_notify.assert_called_once()
    assert mock_notify.call_args.kwargs["strict"] is True


def test_no_correction_when_broker_and_db_quantities_already_match():
    reconciliation = _reconciliation_with_mock_broker()
    reconciliation.broker.fetch_closed_orders.return_value = [
        {"symbol": "AAPL", "filled_qty": "100", "status": "filled"}
    ]
    cur = MagicMock()
    cur.fetchone.return_value = ("trade-123", 100, "open")

    result = reconciliation.check_partial_fills(cur)

    assert result["mismatches"] == 0
    assert not any("UPDATE algo_trades" in c.args[0] for c in cur.execute.call_args_list)
