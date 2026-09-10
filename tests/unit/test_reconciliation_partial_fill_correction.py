"""Verifies DailyReconciliation.check_partial_fills() actually corrects DB quantity
drift against the broker (source of truth), rather than trusting whatever the DB
already believes was filled.

Replaces tests/test_session_281_critical_fixes.py::test_reconciliation_must_handle_partial_fills,
which was left as an unconditional pytest.skip() marked "AUDIT TODO (Session 282)"
for two sessions - it never actually verified the 100-requested/60-filled scenario
its own docstring described.
"""

from datetime import timedelta, timezone
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
        {"symbol": "AAPL", "filled_qty": "60", "status": "partially_filled", "side": "buy"}
    ]
    cur = MagicMock()
    cur.fetchone.return_value = ("trade-123", 100, "open")

    with patch("algo.infrastructure.reconciliation_fill_and_account.notify"):
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
        {"symbol": "AAPL", "filled_qty": "60", "status": "partially_filled", "side": "buy"}
    ]
    cur = MagicMock()
    cur.fetchone.return_value = ("trade-123", 100, "open")

    with patch("algo.infrastructure.reconciliation_fill_and_account.notify") as mock_notify:
        reconciliation.check_partial_fills(cur)

    mock_notify.assert_called_once()
    assert mock_notify.call_args.kwargs["strict"] is True


def test_notify_failure_does_not_discard_the_already_applied_correction():
    """CRITICAL FIX regression: check_partial_fills's UPDATE runs inside the single
    `with DatabaseContext("write") as cur:` block phase4_reconciliation.py opens around
    the whole call. If the operator-alert notify() raises and that propagates out of
    check_partial_fills, it rolls back the transaction - discarding a real, already-
    verified correction (DB quantity fixed to match Alpaca, the source of truth) just
    because the alert channel was flaky. The fix must swallow the notify failure and
    still return the correction in its result."""
    reconciliation = _reconciliation_with_mock_broker()
    reconciliation.broker.fetch_closed_orders.return_value = [
        {"symbol": "AAPL", "filled_qty": "60", "status": "partially_filled", "side": "buy"}
    ]
    cur = MagicMock()
    cur.fetchone.return_value = ("trade-123", 100, "open")

    with patch(
        "algo.infrastructure.reconciliation_fill_and_account.notify", side_effect=RuntimeError("alert channel down")
    ):
        result = reconciliation.check_partial_fills(cur)

    assert result["mismatches"] == 1
    update_calls = [c for c in cur.execute.call_args_list if "UPDATE algo_trades" in c.args[0]]
    assert len(update_calls) == 1
    assert update_calls[0].args[1] == (60, "trade-123")


def test_sub_one_share_drift_is_detected_and_corrected_with_precision():
    """CRITICAL FIX regression: the mismatch check used to compare int(db_qty) !=
    int(alpaca_filled_qty), truncating fractional shares before comparing. A genuine
    sub-1-share drift (DB=10.9, Alpaca=10.1) truncated to int(10.9)=10 == int(10.1)=10 and
    was silently classified as "no mismatch" - unlike the equivalent bug in
    alpaca_sync_manager.py, HERE the comparison gates the correction UPDATE itself, so this
    left algo_trades.entry_quantity permanently wrong with no way for a later pass to catch
    it. Must detect the drift AND write the precise fractional value (not a truncated int)
    to the numeric(_, 4) entry_quantity column."""
    reconciliation = _reconciliation_with_mock_broker()
    reconciliation.broker.fetch_closed_orders.return_value = [
        {"symbol": "AAPL", "filled_qty": "10.1", "status": "filled", "side": "buy"}
    ]
    cur = MagicMock()
    cur.fetchone.return_value = ("trade-123", 10.9, "open")

    with patch("algo.infrastructure.reconciliation_fill_and_account.notify"):
        result = reconciliation.check_partial_fills(cur)

    assert result["mismatches"] == 1
    assert result["details"][0]["db_quantity"] == 10.9
    assert result["details"][0]["alpaca_filled"] == 10.1

    update_calls = [c for c in cur.execute.call_args_list if "UPDATE algo_trades" in c.args[0]]
    assert len(update_calls) == 1
    assert update_calls[0].args[1] == (10.1, "trade-123"), (
        "must write the precise fractional value, not a truncated int"
    )


def test_no_correction_when_broker_and_db_quantities_already_match():
    reconciliation = _reconciliation_with_mock_broker()
    reconciliation.broker.fetch_closed_orders.return_value = [
        {"symbol": "AAPL", "filled_qty": "100", "status": "filled", "side": "buy"}
    ]
    cur = MagicMock()
    cur.fetchone.return_value = ("trade-123", 100, "open")

    result = reconciliation.check_partial_fills(cur)

    assert result["mismatches"] == 0
    assert not any("UPDATE algo_trades" in c.args[0] for c in cur.execute.call_args_list)


def test_partial_exit_sell_order_does_not_corrupt_entry_quantity():
    """CRITICAL FIX regression: fetch_closed_orders() has no side filter, so a T1/T2
    partial-exit SELL order for a still-open trade (status stays in TradeStatus.all_open()
    until the final leg closes it) used to match the same WHERE clause as a real entry
    fill. Its filled_qty is the smaller exit quantity, not the original entry size - before
    the fix, this silently shrank entry_quantity to the partial-exit amount, corrupting
    original_cost_basis/original_risk_dollars (and therefore pnl_pct/exit_r_multiple) for
    every trade that used a partial exit. A sell order must be skipped entirely here."""
    reconciliation = _reconciliation_with_mock_broker()
    reconciliation.broker.fetch_closed_orders.return_value = [
        {"symbol": "AAPL", "filled_qty": "40", "status": "filled", "side": "sell"}
    ]
    cur = MagicMock()
    cur.fetchone.return_value = ("trade-123", 100, "open")  # DB still has the full entry size

    result = reconciliation.check_partial_fills(cur)

    assert result["mismatches"] == 0
    assert not any("SELECT trade_id" in c.args[0] for c in cur.execute.call_args_list), (
        "a sell order should never even reach the DB lookup - it's not an entry fill"
    )
    assert not any("UPDATE algo_trades" in c.args[0] for c in cur.execute.call_args_list)


def test_pyramided_position_fill_correction_binds_to_the_right_trade_via_client_order_id():
    """REAL-MONEY-READINESS FIX regression (2026-09-06): with 2+ open algo_trades rows for
    the same symbol (a pyramided position - a real supported case, see position_sizer.py),
    the old `WHERE symbol = %s ... ORDER BY trade_date DESC LIMIT 1` query resolved to the
    SAME "most recent" trade_id regardless of which order in the closed-orders list was
    being checked - an older pyramid leg's own fill-quantity correction would misattribute
    onto the newer leg's trade_id. The fix must bind by algo_trades.idempotency_key (the
    same value order_manager.send_bracket_order() submits to Alpaca as client_order_id) so
    each order corrects only its own trade."""
    reconciliation = _reconciliation_with_mock_broker()
    reconciliation.broker.fetch_closed_orders.return_value = [
        {"symbol": "AAPL", "client_order_id": "idem-old-leg", "filled_qty": "48", "status": "filled", "side": "buy"}
    ]
    cur = MagicMock()
    # The client_order_id-bound query finds the OLDER pyramid leg (trade-100, entry_quantity=50
    # in DB vs Alpaca's actual 48) - if the fix regressed to symbol-only matching, this would
    # instead find/correct the NEWER leg (trade-200) since that's what "ORDER BY trade_date
    # DESC LIMIT 1" would return.
    cur.fetchone.return_value = ("trade-100", 50, "open")

    with patch("algo.infrastructure.reconciliation_fill_and_account.notify"):
        result = reconciliation.check_partial_fills(cur)

    assert result["mismatches"] == 1
    assert result["details"][0]["trade_id"] == "trade-100"

    lookup_calls = [c for c in cur.execute.call_args_list if "SELECT trade_id" in c.args[0]]
    assert len(lookup_calls) == 1, (
        "should resolve on the first (idempotency_key-bound) lookup, no symbol fallback needed"
    )
    assert "idempotency_key = %s" in lookup_calls[0].args[0]
    assert lookup_calls[0].args[1][0] == "idem-old-leg"

    update_calls = [c for c in cur.execute.call_args_list if "UPDATE algo_trades" in c.args[0]]
    assert len(update_calls) == 1
    assert update_calls[0].args[1] == (48, "trade-100")


def test_missing_client_order_id_falls_back_to_symbol_match():
    """Orders with no client_order_id echoed back (shouldn't happen for anything this
    system submitted, but must not be silently skipped) must still fall back to the old
    symbol-only match."""
    reconciliation = _reconciliation_with_mock_broker()
    reconciliation.broker.fetch_closed_orders.return_value = [
        {"symbol": "AAPL", "filled_qty": "60", "status": "partially_filled", "side": "buy"}
    ]
    cur = MagicMock()
    cur.fetchone.return_value = ("trade-123", 100, "open")

    with patch("algo.infrastructure.reconciliation_fill_and_account.notify"):
        result = reconciliation.check_partial_fills(cur)

    assert result["mismatches"] == 1
    lookup_calls = [c for c in cur.execute.call_args_list if "SELECT trade_id" in c.args[0]]
    assert len(lookup_calls) == 1
    assert "WHERE symbol = %s" in lookup_calls[0].args[0]


def test_lookup_query_covers_pending_and_paper_pending_statuses():
    """CRITICAL FIX regression: the DB lookup previously hardcoded
    ('open','filled','partially_filled','active'), omitting 'pending'/'paper_pending' - the
    exact two statuses a trade sits in when "Alpaca fills part of an order and then network
    fails before we can sync" (this function's own docstring). A trade stuck at 'pending' in
    our DB while Alpaca's closed-orders feed already shows it filled must still be found."""
    from utils.trading import TradeStatus

    reconciliation = _reconciliation_with_mock_broker()
    reconciliation.broker.fetch_closed_orders.return_value = [
        {"symbol": "AAPL", "filled_qty": "60", "status": "filled", "side": "buy"}
    ]
    cur = MagicMock()
    cur.fetchone.return_value = ("trade-123", 100, "pending")

    reconciliation.check_partial_fills(cur)

    lookup_calls = [c for c in cur.execute.call_args_list if "SELECT trade_id" in c.args[0]]
    assert lookup_calls, "expected a SELECT trade_id lookup against algo_trades"
    sql_text, params = lookup_calls[0].args
    for status in TradeStatus.all_open():
        assert status in params, f"expected {status!r} among lookup query params, got {params!r}"


def test_fetches_closed_orders_with_a_bounded_since_window():
    """REGRESSION for the 2026-09-08 fix: check_partial_fills() used to call
    fetch_closed_orders() with no `since` at all - relying entirely on Alpaca's own
    undocumented default page size/window (no `after`, no explicit `limit`), unlike its
    sibling reconcile_exit_fills() which has always bounded to a 2-day window. A fill
    reconciliation whose own docstring is "network fails before we can sync" needs a
    reliable, explicit lookback window, not an implicit "most recent N orders overall"
    default that could silently exclude an older unreconciled fill on a busy trading day.
    """
    reconciliation = _reconciliation_with_mock_broker()
    reconciliation.broker.fetch_closed_orders.return_value = []
    cur = MagicMock()

    reconciliation.check_partial_fills(cur)

    reconciliation.broker.fetch_closed_orders.assert_called_once()
    _, kwargs = reconciliation.broker.fetch_closed_orders.call_args
    since = kwargs["since"]
    assert since.tzinfo is not None
    from datetime import datetime as _dt

    age = _dt.now(timezone.utc) - since
    # Must be bounded (not None/unbounded) and match the 2-day sibling convention -
    # generous tolerance only for test wall-clock slack, not a loose spec.
    assert timedelta(days=1, hours=23) < age < timedelta(days=2, hours=1)
