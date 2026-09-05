"""Regression test for Phase 9's proactive stop-loss protection check
(_verify_open_position_stop_loss_protection_step), added 2026-09-04 as part of the
real-money-readiness push, and updated 2026-09-05 to auto-repair a missing leg instead
of only alerting a human.

FINDING: entry bracket orders are submitted with time_in_force=day
(order_manager.py's _build_bracket_order_payload) on a strategy that holds positions
many days. Whether Alpaca expires the OCO stop-loss/take-profit legs at end-of-day once
live is undocumented either way - but the only existing code that would ever notice a
missing leg (OrderManager.sync_bracket_stop_loss) only runs REACTIVELY, when
position_monitor recommends RAISE_STOP. A flat or drawing-down position - exactly when
protection matters most - had no trigger that would ever re-check it. This step closes
that gap by proactively verifying every open position's bracket order every
reconciliation cycle, using the read-only OrderManager.check_stop_loss_leg_live (never
sync_bracket_stop_loss, which would replace/cancel-recreate the leg on every check).

UPDATED 2026-09-05: a real-money go-live decision (nobody reliably watches alerts in
real time) means a detected gap is now auto-repaired via
OrderManager.submit_standalone_protective_stop, with the alert reserved for the case
where auto-repair itself fails.
"""

from unittest.mock import MagicMock, patch

from algo.orchestrator.phase9_reconciliation import _verify_open_position_stop_loss_protection_step


def _make_db_context(fetchall_result=None, fetchone_results=None):
    """Builds a DatabaseContext mock queue: first call returns fetchall_result via
    cursor.fetchall(), subsequent calls return fetchone_results in order via
    cursor.fetchone(). Any further calls (e.g. a repair's UPDATE write) get an
    unconfigured MagicMock cursor, which is fine for calls that don't read results."""
    contexts = []

    if fetchall_result is not None:
        cur = MagicMock()
        cur.fetchall.return_value = fetchall_result
        ctx = MagicMock()
        ctx.__enter__.return_value = cur
        ctx.__exit__.return_value = False
        contexts.append(ctx)

    for fetchone_result in fetchone_results or []:
        cur = MagicMock()
        cur.fetchone.return_value = fetchone_result
        ctx = MagicMock()
        ctx.__enter__.return_value = cur
        ctx.__exit__.return_value = False
        contexts.append(ctx)

    def fake_database_context(role):
        if contexts:
            return contexts.pop(0)
        ctx = MagicMock()
        ctx.__enter__.return_value = MagicMock()
        ctx.__exit__.return_value = False
        return ctx

    return fake_database_context


def test_skips_entirely_when_no_alpaca_credentials():
    """Paper mode with no credentials configured - nothing to verify against a broker,
    must not attempt any DB query or Alpaca call."""
    log_calls = []

    mock_sync_mgr = MagicMock()
    mock_sync_mgr.alpaca_key = None
    mock_sync_mgr.alpaca_secret = None

    with (
        patch("algo.infrastructure.alpaca_sync_manager.AlpacaSyncManager", return_value=mock_sync_mgr),
        patch("algo.orchestrator.phase9_reconciliation.DatabaseContext") as mock_db,
    ):
        _verify_open_position_stop_loss_protection_step(lambda *a: log_calls.append(a), config={})

    mock_db.assert_not_called()
    assert log_calls[0][2] == "info"
    assert "skipped" in log_calls[0][3]


def test_no_open_positions_is_a_clean_noop():
    log_calls = []

    mock_sync_mgr = MagicMock()
    mock_sync_mgr.alpaca_key = "key"
    mock_sync_mgr.alpaca_secret = "secret"
    mock_sync_mgr.alpaca_base_url = "https://paper-api.alpaca.markets"

    with (
        patch("algo.infrastructure.alpaca_sync_manager.AlpacaSyncManager", return_value=mock_sync_mgr),
        patch(
            "algo.orchestrator.phase9_reconciliation.DatabaseContext",
            side_effect=_make_db_context(fetchall_result=[]),
        ),
    ):
        _verify_open_position_stop_loss_protection_step(lambda *a: log_calls.append(a), config={})

    assert log_calls[0][2] == "info"
    assert "no open positions" in log_calls[0][3]


def test_protected_position_does_not_alert_or_repair():
    log_calls = []

    mock_sync_mgr = MagicMock()
    mock_sync_mgr.alpaca_key = "key"
    mock_sync_mgr.alpaca_secret = "secret"
    mock_sync_mgr.alpaca_base_url = "https://paper-api.alpaca.markets"

    mock_order_mgr = MagicMock()
    mock_order_mgr.check_stop_loss_leg_live.return_value = {
        "checked": True,
        "has_live_stop_loss": True,
        "message": "stop-loss leg live",
    }

    # (id, symbol, trade_ids_arr, quantity, current_stop_price, standalone_stop_order_id)
    open_positions = [(1, "AAPL", ["trade-1"], 10.0, 150.0, None)]
    fake_db = _make_db_context(fetchall_result=open_positions, fetchone_results=[("order-abc",)])

    with (
        patch("algo.infrastructure.alpaca_sync_manager.AlpacaSyncManager", return_value=mock_sync_mgr),
        patch("algo.trading.order_manager.OrderManager", return_value=mock_order_mgr),
        patch("algo.orchestrator.phase9_reconciliation.DatabaseContext", side_effect=fake_db),
        patch("algo.orchestrator.phase9_stop_loss_repair.DatabaseContext", side_effect=fake_db),
        patch("algo.reporting.notifications.notify") as mock_notify,
    ):
        _verify_open_position_stop_loss_protection_step(lambda *a: log_calls.append(a), config={})

    mock_order_mgr.check_stop_loss_leg_live.assert_called_once_with("order-abc")
    mock_order_mgr.submit_standalone_protective_stop.assert_not_called()
    mock_notify.assert_not_called()
    assert log_calls[-1][2] == "success"
    assert "verified 1" in log_calls[-1][3]


def test_missing_stop_loss_leg_auto_repairs_and_sends_warning_not_critical():
    """The core case this check exists for: a broker-side protective leg has gone
    missing on an open position. Must self-heal via a standalone protective stop rather
    than only alerting - and the resulting notification must be a non-blocking warning
    (auto-repair succeeded), not a critical page."""
    log_calls = []

    mock_sync_mgr = MagicMock()
    mock_sync_mgr.alpaca_key = "key"
    mock_sync_mgr.alpaca_secret = "secret"
    mock_sync_mgr.alpaca_base_url = "https://paper-api.alpaca.markets"

    mock_order_mgr = MagicMock()
    mock_order_mgr.check_stop_loss_leg_live.return_value = {
        "checked": True,
        "has_live_stop_loss": False,
        "message": "No live stop-loss leg on order order-xyz - leg statuses: [('limit', 'new')]",
    }
    mock_order_mgr.submit_standalone_protective_stop.return_value = {
        "success": True,
        "order_id": "new-stop-order-1",
        "message": "Standalone protective stop submitted for TSLA",
    }

    open_positions = [(7, "TSLA", ["trade-99"], 25.0, 210.50, None)]
    fake_db = _make_db_context(fetchall_result=open_positions, fetchone_results=[("order-xyz",)])

    with (
        patch("algo.infrastructure.alpaca_sync_manager.AlpacaSyncManager", return_value=mock_sync_mgr),
        patch("algo.trading.order_manager.OrderManager", return_value=mock_order_mgr),
        patch("algo.orchestrator.phase9_reconciliation.DatabaseContext", side_effect=fake_db),
        patch("algo.orchestrator.phase9_stop_loss_repair.DatabaseContext", side_effect=fake_db),
        patch("algo.reporting.notifications.notify") as mock_notify,
    ):
        _verify_open_position_stop_loss_protection_step(lambda *a: log_calls.append(a), config={})

    mock_order_mgr.submit_standalone_protective_stop.assert_called_once_with("TSLA", 25.0, 210.50)
    mock_notify.assert_called_once()
    args, kwargs = mock_notify.call_args
    assert args[0] == "warning"
    assert "TSLA" in kwargs["message"]
    assert log_calls[-1][2] == "warn"
    assert "TSLA" in log_calls[-1][3]


def test_auto_repair_failure_triggers_critical_alert():
    """When the leg is missing AND the repair submission itself fails, that's the one
    case that still needs a human - must alert critically, not silently give up."""
    log_calls = []

    mock_sync_mgr = MagicMock()
    mock_sync_mgr.alpaca_key = "key"
    mock_sync_mgr.alpaca_secret = "secret"
    mock_sync_mgr.alpaca_base_url = "https://paper-api.alpaca.markets"

    mock_order_mgr = MagicMock()
    mock_order_mgr.check_stop_loss_leg_live.return_value = {
        "checked": True,
        "has_live_stop_loss": False,
        "message": "No live stop-loss leg",
    }
    mock_order_mgr.submit_standalone_protective_stop.return_value = {
        "success": False,
        "message": "Failed to submit protective stop for TSLA after 3 attempts: 500 error",
    }

    open_positions = [(7, "TSLA", ["trade-99"], 25.0, 210.50, None)]
    fake_db = _make_db_context(fetchall_result=open_positions, fetchone_results=[("order-xyz",)])

    with (
        patch("algo.infrastructure.alpaca_sync_manager.AlpacaSyncManager", return_value=mock_sync_mgr),
        patch("algo.trading.order_manager.OrderManager", return_value=mock_order_mgr),
        patch("algo.orchestrator.phase9_reconciliation.DatabaseContext", side_effect=fake_db),
        patch("algo.orchestrator.phase9_stop_loss_repair.DatabaseContext", side_effect=fake_db),
        patch("algo.reporting.notifications.notify") as mock_notify,
    ):
        _verify_open_position_stop_loss_protection_step(lambda *a: log_calls.append(a), config={})

    mock_notify.assert_called_once()
    args, kwargs = mock_notify.call_args
    assert args[0] == "critical"
    assert "TSLA" in kwargs["message"]
    assert log_calls[-1][2] == "critical"
    assert "TSLA" in log_calls[-1][3]


def test_missing_quantity_or_stop_price_is_unrepairable_not_a_crash():
    """Can't safely auto-repair without knowing size/price - must fall back to a
    critical alert rather than guessing or crashing."""
    log_calls = []

    mock_sync_mgr = MagicMock()
    mock_sync_mgr.alpaca_key = "key"
    mock_sync_mgr.alpaca_secret = "secret"
    mock_sync_mgr.alpaca_base_url = "https://paper-api.alpaca.markets"

    mock_order_mgr = MagicMock()
    mock_order_mgr.check_stop_loss_leg_live.return_value = {
        "checked": True,
        "has_live_stop_loss": False,
        "message": "No live stop-loss leg",
    }

    open_positions = [(7, "TSLA", ["trade-99"], 25.0, None, None)]
    fake_db = _make_db_context(fetchall_result=open_positions, fetchone_results=[("order-xyz",)])

    with (
        patch("algo.infrastructure.alpaca_sync_manager.AlpacaSyncManager", return_value=mock_sync_mgr),
        patch("algo.trading.order_manager.OrderManager", return_value=mock_order_mgr),
        patch("algo.orchestrator.phase9_reconciliation.DatabaseContext", side_effect=fake_db),
        patch("algo.orchestrator.phase9_stop_loss_repair.DatabaseContext", side_effect=fake_db),
        patch("algo.reporting.notifications.notify") as mock_notify,
    ):
        _verify_open_position_stop_loss_protection_step(lambda *a: log_calls.append(a), config={})

    mock_order_mgr.submit_standalone_protective_stop.assert_not_called()
    mock_notify.assert_called_once()
    assert mock_notify.call_args[0][0] == "critical"
    assert log_calls[-1][2] == "critical"


def test_already_repaired_position_with_live_standalone_stop_is_skipped():
    """A prior cycle's repair is still resting live at the broker - must not re-check
    the (now-irrelevant) original bracket or submit a duplicate protective stop."""
    log_calls = []

    mock_sync_mgr = MagicMock()
    mock_sync_mgr.alpaca_key = "key"
    mock_sync_mgr.alpaca_secret = "secret"
    mock_sync_mgr.alpaca_base_url = "https://paper-api.alpaca.markets"

    mock_order_mgr = MagicMock()
    mock_order_mgr.is_order_still_live.return_value = True

    open_positions = [(7, "TSLA", ["trade-99"], 25.0, 210.50, "prior-repair-order-1")]
    fake_db = _make_db_context(fetchall_result=open_positions, fetchone_results=[])

    with (
        patch("algo.infrastructure.alpaca_sync_manager.AlpacaSyncManager", return_value=mock_sync_mgr),
        patch("algo.trading.order_manager.OrderManager", return_value=mock_order_mgr),
        patch("algo.orchestrator.phase9_reconciliation.DatabaseContext", side_effect=fake_db),
        patch("algo.orchestrator.phase9_stop_loss_repair.DatabaseContext", side_effect=fake_db),
        patch("algo.reporting.notifications.notify") as mock_notify,
    ):
        _verify_open_position_stop_loss_protection_step(lambda *a: log_calls.append(a), config={})

    mock_order_mgr.check_stop_loss_leg_live.assert_not_called()
    mock_order_mgr.submit_standalone_protective_stop.assert_not_called()
    mock_notify.assert_not_called()
    assert log_calls[-1][2] == "success"
    assert "verified 1" in log_calls[-1][3]


def test_stale_prior_repair_falls_through_to_recheck_original_bracket():
    """A previously-placed repair order is no longer live (filled/cancelled) - must
    fall through to the normal check-and-repair flow rather than trusting a dead
    reference forever."""
    log_calls = []

    mock_sync_mgr = MagicMock()
    mock_sync_mgr.alpaca_key = "key"
    mock_sync_mgr.alpaca_secret = "secret"
    mock_sync_mgr.alpaca_base_url = "https://paper-api.alpaca.markets"

    mock_order_mgr = MagicMock()
    mock_order_mgr.is_order_still_live.return_value = False
    mock_order_mgr.check_stop_loss_leg_live.return_value = {
        "checked": True,
        "has_live_stop_loss": False,
        "message": "No live stop-loss leg",
    }
    mock_order_mgr.submit_standalone_protective_stop.return_value = {
        "success": True,
        "order_id": "new-stop-order-2",
        "message": "Standalone protective stop submitted for TSLA",
    }

    open_positions = [(7, "TSLA", ["trade-99"], 25.0, 210.50, "stale-repair-order")]
    fake_db = _make_db_context(fetchall_result=open_positions, fetchone_results=[("order-xyz",)])

    with (
        patch("algo.infrastructure.alpaca_sync_manager.AlpacaSyncManager", return_value=mock_sync_mgr),
        patch("algo.trading.order_manager.OrderManager", return_value=mock_order_mgr),
        patch("algo.orchestrator.phase9_reconciliation.DatabaseContext", side_effect=fake_db),
        patch("algo.orchestrator.phase9_stop_loss_repair.DatabaseContext", side_effect=fake_db),
        patch("algo.reporting.notifications.notify") as mock_notify,
    ):
        _verify_open_position_stop_loss_protection_step(lambda *a: log_calls.append(a), config={})

    mock_order_mgr.check_stop_loss_leg_live.assert_called_once_with("order-xyz")
    mock_order_mgr.submit_standalone_protective_stop.assert_called_once()
    assert mock_notify.call_args[0][0] == "warning"
    assert log_calls[-1][2] == "warn"


def test_notify_failure_does_not_crash_the_check():
    """Notification delivery failing must not prevent the check itself from completing
    and logging its phase result - matches this file's own established pattern for
    every other best-effort notify() call site."""
    log_calls = []

    mock_sync_mgr = MagicMock()
    mock_sync_mgr.alpaca_key = "key"
    mock_sync_mgr.alpaca_secret = "secret"
    mock_sync_mgr.alpaca_base_url = "https://paper-api.alpaca.markets"

    mock_order_mgr = MagicMock()
    mock_order_mgr.check_stop_loss_leg_live.return_value = {
        "checked": True,
        "has_live_stop_loss": False,
        "message": "No live stop-loss leg",
    }
    mock_order_mgr.submit_standalone_protective_stop.return_value = {
        "success": False,
        "message": "broker unreachable",
    }

    open_positions = [(7, "TSLA", ["trade-99"], 25.0, 210.50, None)]
    fake_db = _make_db_context(fetchall_result=open_positions, fetchone_results=[("order-xyz",)])

    with (
        patch("algo.infrastructure.alpaca_sync_manager.AlpacaSyncManager", return_value=mock_sync_mgr),
        patch("algo.trading.order_manager.OrderManager", return_value=mock_order_mgr),
        patch("algo.orchestrator.phase9_reconciliation.DatabaseContext", side_effect=fake_db),
        patch("algo.orchestrator.phase9_stop_loss_repair.DatabaseContext", side_effect=fake_db),
        patch("algo.reporting.notifications.notify", side_effect=RuntimeError("smtp down")),
    ):
        # Must not raise despite notify() failing internally.
        _verify_open_position_stop_loss_protection_step(lambda *a: log_calls.append(a), config={})

    assert log_calls[-1][2] == "critical"


def test_position_with_no_trade_ids_arr_is_skipped_not_crashed():
    log_calls = []

    mock_sync_mgr = MagicMock()
    mock_sync_mgr.alpaca_key = "key"
    mock_sync_mgr.alpaca_secret = "secret"
    mock_sync_mgr.alpaca_base_url = "https://paper-api.alpaca.markets"

    open_positions = [(3, "ORPHAN", None, 5.0, 90.0, None)]
    fake_db = _make_db_context(fetchall_result=open_positions, fetchone_results=[])

    with (
        patch("algo.infrastructure.alpaca_sync_manager.AlpacaSyncManager", return_value=mock_sync_mgr),
        patch("algo.trading.order_manager.OrderManager") as mock_order_mgr_cls,
        patch("algo.orchestrator.phase9_reconciliation.DatabaseContext", side_effect=fake_db),
    ):
        _verify_open_position_stop_loss_protection_step(lambda *a: log_calls.append(a), config={})

    mock_order_mgr_cls.return_value.check_stop_loss_leg_live.assert_not_called()
    assert log_calls[-1][2] == "success"


def test_live_leg_with_stale_qty_resizes_instead_of_reporting_protected():
    """FINDING (real-money audit, 2026-09-05): leg *presence* alone isn't proof of
    protection - a partial-exit resize (executor_exit_handler.py) can fail and only log,
    leaving a live stop leg sized for the PRE-partial-exit share count. Must detect the
    qty mismatch and resize in place rather than reporting "protected" on presence alone."""
    log_calls = []

    mock_sync_mgr = MagicMock()
    mock_sync_mgr.alpaca_key = "key"
    mock_sync_mgr.alpaca_secret = "secret"
    mock_sync_mgr.alpaca_base_url = "https://paper-api.alpaca.markets"

    mock_order_mgr = MagicMock()
    mock_order_mgr.check_stop_loss_leg_live.return_value = {
        "checked": True,
        "has_live_stop_loss": True,
        "leg_qty": 50.0,  # stale: sized for the original position, before a partial exit
        "message": "stop-loss leg live",
    }
    mock_order_mgr.sync_bracket_stop_loss.return_value = {"success": True, "synced": True}

    # Position now holds only 25 shares after a partial exit, but the resting leg is 50.
    open_positions = [(7, "TSLA", ["trade-99"], 25.0, 210.50, None)]
    fake_db = _make_db_context(fetchall_result=open_positions, fetchone_results=[("order-xyz",)])

    with (
        patch("algo.infrastructure.alpaca_sync_manager.AlpacaSyncManager", return_value=mock_sync_mgr),
        patch("algo.trading.order_manager.OrderManager", return_value=mock_order_mgr),
        patch("algo.orchestrator.phase9_reconciliation.DatabaseContext", side_effect=fake_db),
        patch("algo.orchestrator.phase9_stop_loss_repair.DatabaseContext", side_effect=fake_db),
        patch("algo.reporting.notifications.notify"),
    ):
        _verify_open_position_stop_loss_protection_step(lambda *a: log_calls.append(a), config={})

    mock_order_mgr.sync_bracket_stop_loss.assert_called_once_with("order-xyz", 210.50, new_qty=25.0)
    mock_order_mgr.submit_standalone_protective_stop.assert_not_called()
    # A repair happened (like the missing-leg case), so this logs as a warning, not a
    # plain success - the resize itself is verified via the mock call assertion above.
    assert log_calls[-1][2] == "warn"
    assert "TSLA" in log_calls[-1][3]


def test_live_leg_with_matching_qty_is_protected_no_resize():
    """The normal case: leg present and correctly sized - must not call resize/repair."""
    log_calls = []

    mock_sync_mgr = MagicMock()
    mock_sync_mgr.alpaca_key = "key"
    mock_sync_mgr.alpaca_secret = "secret"
    mock_sync_mgr.alpaca_base_url = "https://paper-api.alpaca.markets"

    mock_order_mgr = MagicMock()
    mock_order_mgr.check_stop_loss_leg_live.return_value = {
        "checked": True,
        "has_live_stop_loss": True,
        "leg_qty": 25.0,
        "message": "stop-loss leg live",
    }

    open_positions = [(7, "TSLA", ["trade-99"], 25.0, 210.50, None)]
    fake_db = _make_db_context(fetchall_result=open_positions, fetchone_results=[("order-xyz",)])

    with (
        patch("algo.infrastructure.alpaca_sync_manager.AlpacaSyncManager", return_value=mock_sync_mgr),
        patch("algo.trading.order_manager.OrderManager", return_value=mock_order_mgr),
        patch("algo.orchestrator.phase9_reconciliation.DatabaseContext", side_effect=fake_db),
        patch("algo.orchestrator.phase9_stop_loss_repair.DatabaseContext", side_effect=fake_db),
        patch("algo.reporting.notifications.notify") as mock_notify,
    ):
        _verify_open_position_stop_loss_protection_step(lambda *a: log_calls.append(a), config={})

    mock_order_mgr.sync_bracket_stop_loss.assert_not_called()
    mock_notify.assert_not_called()
    assert log_calls[-1][2] == "success"


def test_unchecked_result_paper_local_order_is_not_counted_as_unprotected():
    """A LOCAL-/PENDING- order id (paper-mode synthetic order, never a real broker
    bracket) must not be flagged as missing protection - there was never anything to
    protect it in the first place."""
    log_calls = []

    mock_sync_mgr = MagicMock()
    mock_sync_mgr.alpaca_key = "key"
    mock_sync_mgr.alpaca_secret = "secret"
    mock_sync_mgr.alpaca_base_url = "https://paper-api.alpaca.markets"

    mock_order_mgr = MagicMock()
    mock_order_mgr.check_stop_loss_leg_live.return_value = {
        "checked": False,
        "has_live_stop_loss": None,
        "message": "No live Alpaca order to check (paper/local mode)",
    }

    open_positions = [(9, "PAPERSYM", ["trade-1"], 8.0, 42.0, None)]
    fake_db = _make_db_context(fetchall_result=open_positions, fetchone_results=[("LOCAL-abc123",)])

    with (
        patch("algo.infrastructure.alpaca_sync_manager.AlpacaSyncManager", return_value=mock_sync_mgr),
        patch("algo.trading.order_manager.OrderManager", return_value=mock_order_mgr),
        patch("algo.orchestrator.phase9_reconciliation.DatabaseContext", side_effect=fake_db),
        patch("algo.orchestrator.phase9_stop_loss_repair.DatabaseContext", side_effect=fake_db),
        patch("algo.reporting.notifications.notify") as mock_notify,
    ):
        _verify_open_position_stop_loss_protection_step(lambda *a: log_calls.append(a), config={})

    mock_notify.assert_not_called()
    assert log_calls[-1][2] == "success"
    assert "verified 0" in log_calls[-1][3]
