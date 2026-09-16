"""Regression test for scripts/flatten_all_positions.py, the manual emergency-flatten tool.

Built 2026-08-24 (real-money-readiness /goal session) after an operational-readiness audit
found scripts/manage_halt_flag.py can stop new entries but nothing in this codebase could
close EXISTING open positions on operator demand - see
memory/pre_live_money_operational_audit_20260824.md, finding #4.

This test mocks every external dependency (DB, halt manager, TradeExecutor, quote fetcher) -
it verifies the script's own control flow (confirm/reason gating, halt-before-flatten
ordering, per-symbol success/failure accounting, exit codes), not the underlying exit
mechanics themselves, which are already covered by executor_exit_handler.py's own extensive
test suite. --status was separately live-verified against the real local DB (read-only,
listed the 4 real open positions correctly) - not re-tested here since it's a thin DB read.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

import scripts.flatten_all_positions as flatten_all_positions


def _run(argv, broker_only=(), remaining_after_flatten=()):
    """remaining_after_flatten: positions the broker still reports once the run finishes -
    feeds the post-flatten verification pass (2026-09-10 fix). Defaults to empty, i.e. the
    broker confirms the account is actually flat, independent of whatever the run's own
    per-step success/failure accounting believed."""
    with (
        patch.object(sys, "argv", ["flatten_all_positions.py", *argv]),
        patch.object(flatten_all_positions, "_fetch_broker_only_symbols", return_value=list(broker_only)),
        patch.object(flatten_all_positions, "_fetch_broker_positions", return_value=list(remaining_after_flatten)),
    ):
        return flatten_all_positions.main()


class TestArgumentGating:
    def test_no_flags_errors(self):
        with patch.object(sys, "argv", ["flatten_all_positions.py"]):
            with patch.object(flatten_all_positions, "_fetch_open_trades", return_value=[]):
                with pytest.raises(SystemExit):
                    flatten_all_positions.main()

    def test_confirm_without_reason_errors(self):
        with patch.object(sys, "argv", ["flatten_all_positions.py", "--confirm"]):
            with patch.object(flatten_all_positions, "_fetch_open_trades", return_value=[]):
                with pytest.raises(SystemExit):
                    flatten_all_positions.main()


class TestStatusMode:
    def test_status_lists_open_trades_without_closing(self, capsys):
        with patch.object(
            flatten_all_positions,
            "_fetch_open_trades",
            return_value=[(1, "AAPL", "filled", "ord-a"), (2, "MSFT", "filled", "ord-m")],
        ):
            with (
                patch.object(flatten_all_positions, "HaltFlagManager") as mock_halt_cls,
                patch.object(flatten_all_positions, "AlgoConfig", return_value={"execution_mode": "paper"}),
            ):
                exit_code = _run(["--status"])

        assert exit_code == 0
        mock_halt_cls.assert_not_called()
        out = capsys.readouterr().out
        assert "AAPL" in out and "MSFT" in out
        assert "Open positions (DB-tracked): 2" in out


class TestFlattenFlow:
    def test_no_open_positions_is_a_noop(self, capsys):
        with (
            patch.object(flatten_all_positions, "_fetch_open_trades", return_value=[]),
            patch.object(flatten_all_positions, "AlgoConfig", return_value={"execution_mode": "paper"}),
        ):
            with patch.object(flatten_all_positions, "HaltFlagManager") as mock_halt_cls:
                exit_code = _run(["--confirm", "--reason", "test"])

        assert exit_code == 0
        mock_halt_cls.assert_not_called()
        assert "nothing to flatten" in capsys.readouterr().out.lower()

    def test_halt_set_before_any_exit_is_attempted(self):
        """The halt flag must be set before the first exit_trade call - regression coverage
        for the ordering: flattening without halting first would let a concurrent orchestrator
        run open a new position while this script is still closing others."""
        call_order = []
        mock_halt_manager = MagicMock()
        mock_halt_manager.set_halt_flag.side_effect = lambda *a, **k: call_order.append("halt") or True
        mock_executor = MagicMock()
        mock_executor.exit_trade.side_effect = lambda **k: call_order.append("exit") or {"success": True}

        with (
            patch.object(flatten_all_positions, "_fetch_open_trades", return_value=[(1, "AAPL", "filled", "ord-a")]),
            patch.object(flatten_all_positions, "HaltFlagManager", return_value=mock_halt_manager),
            patch.object(flatten_all_positions, "AlgoConfig", return_value={"execution_mode": "paper"}),
            patch.object(flatten_all_positions, "TradeExecutor", return_value=mock_executor),
            patch.object(flatten_all_positions, "fetch_live_quote", return_value=150.0),
        ):
            exit_code = _run(["--confirm", "--reason", "test emergency"])

        assert exit_code == 0
        assert call_order == ["halt", "exit"]

    def test_halt_failure_aborts_before_any_exit(self):
        mock_halt_manager = MagicMock()
        mock_halt_manager.set_halt_flag.return_value = False
        mock_executor = MagicMock()

        with (
            patch.object(flatten_all_positions, "_fetch_open_trades", return_value=[(1, "AAPL", "filled", "ord-a")]),
            patch.object(flatten_all_positions, "HaltFlagManager", return_value=mock_halt_manager),
            patch.object(flatten_all_positions, "TradeExecutor", return_value=mock_executor),
        ):
            exit_code = _run(["--confirm", "--reason", "test emergency"])

        assert exit_code == 1
        mock_executor.exit_trade.assert_not_called()

    def test_all_positions_closed_successfully(self, capsys):
        mock_halt_manager = MagicMock()
        mock_halt_manager.set_halt_flag.return_value = True
        mock_executor = MagicMock()
        mock_executor.exit_trade.return_value = {"success": True}

        with (
            patch.object(
                flatten_all_positions,
                "_fetch_open_trades",
                return_value=[(1, "AAPL", "filled", "ord-a"), (2, "MSFT", "filled", "ord-m")],
            ),
            patch.object(flatten_all_positions, "HaltFlagManager", return_value=mock_halt_manager),
            patch.object(flatten_all_positions, "AlgoConfig", return_value={"execution_mode": "paper"}),
            patch.object(flatten_all_positions, "TradeExecutor", return_value=mock_executor),
            patch.object(flatten_all_positions, "fetch_live_quote", return_value=150.0),
        ):
            exit_code = _run(["--confirm", "--reason", "test emergency"])

        assert exit_code == 0
        assert mock_executor.exit_trade.call_count == 2
        out = capsys.readouterr().out
        assert "2 closed, 0 failed" in out

    def test_exit_reason_tags_manual_emergency_flatten(self):
        mock_halt_manager = MagicMock()
        mock_halt_manager.set_halt_flag.return_value = True
        mock_executor = MagicMock()
        mock_executor.exit_trade.return_value = {"success": True}

        with (
            patch.object(flatten_all_positions, "_fetch_open_trades", return_value=[(1, "AAPL", "filled", "ord-a")]),
            patch.object(flatten_all_positions, "HaltFlagManager", return_value=mock_halt_manager),
            patch.object(flatten_all_positions, "AlgoConfig", return_value={"execution_mode": "paper"}),
            patch.object(flatten_all_positions, "TradeExecutor", return_value=mock_executor),
            patch.object(flatten_all_positions, "fetch_live_quote", return_value=150.0),
        ):
            _run(["--confirm", "--reason", "runaway bug"])

        _, kwargs = mock_executor.exit_trade.call_args
        assert kwargs["exit_fraction"] == 1.0
        assert "MANUAL_EMERGENCY_FLATTEN" in kwargs["exit_reason"]
        assert "runaway bug" in kwargs["exit_reason"]

    def test_quote_failure_marks_symbol_failed_but_continues_others(self, capsys):
        mock_halt_manager = MagicMock()
        mock_halt_manager.set_halt_flag.return_value = True
        mock_executor = MagicMock()
        mock_executor.exit_trade.return_value = {"success": True}

        def quote_side_effect(symbol, *a, **k):
            if symbol == "AAPL":
                raise RuntimeError("quote API down")
            return 150.0

        with (
            patch.object(
                flatten_all_positions,
                "_fetch_open_trades",
                return_value=[(1, "AAPL", "filled", "ord-a"), (2, "MSFT", "filled", "ord-m")],
            ),
            patch.object(flatten_all_positions, "HaltFlagManager", return_value=mock_halt_manager),
            patch.object(flatten_all_positions, "AlgoConfig", return_value={"execution_mode": "paper"}),
            patch.object(flatten_all_positions, "TradeExecutor", return_value=mock_executor),
            patch.object(flatten_all_positions, "fetch_live_quote", side_effect=quote_side_effect),
        ):
            exit_code = _run(["--confirm", "--reason", "test emergency"])

        # AAPL's quote fetch failed but MSFT still got closed - a single symbol's data
        # problem must not abort flattening every other real open position.
        assert exit_code == 1
        assert mock_executor.exit_trade.call_count == 1
        out = capsys.readouterr().out
        assert "1 closed, 1 failed" in out

    def test_exit_failure_reported_and_nonzero_exit(self, capsys):
        mock_halt_manager = MagicMock()
        mock_halt_manager.set_halt_flag.return_value = True
        mock_executor = MagicMock()
        mock_executor.exit_trade.return_value = {"success": False, "message": "broker rejected order"}

        with (
            patch.object(flatten_all_positions, "_fetch_open_trades", return_value=[(1, "AAPL", "filled", "ord-a")]),
            patch.object(flatten_all_positions, "HaltFlagManager", return_value=mock_halt_manager),
            patch.object(flatten_all_positions, "AlgoConfig", return_value={"execution_mode": "paper"}),
            patch.object(flatten_all_positions, "TradeExecutor", return_value=mock_executor),
            patch.object(flatten_all_positions, "fetch_live_quote", return_value=150.0),
        ):
            exit_code = _run(["--confirm", "--reason", "test emergency"])

        assert exit_code == 1
        out = capsys.readouterr().out
        assert "broker rejected order" in out

    def test_data_unavailable_quote_dict_marks_failed_not_crashed(self):
        """fetch_live_quote can return a dict ({"data_unavailable": True, ...}) instead of a
        float in paper-mode sandbox 404/401 cases - must be treated as a failure, not passed
        through to exit_trade's exit_price (which requires a float > 0)."""
        mock_halt_manager = MagicMock()
        mock_halt_manager.set_halt_flag.return_value = True
        mock_executor = MagicMock()

        with (
            patch.object(flatten_all_positions, "_fetch_open_trades", return_value=[(1, "AAPL", "filled", "ord-a")]),
            patch.object(flatten_all_positions, "HaltFlagManager", return_value=mock_halt_manager),
            patch.object(flatten_all_positions, "AlgoConfig", return_value={"execution_mode": "paper"}),
            patch.object(flatten_all_positions, "TradeExecutor", return_value=mock_executor),
            patch.object(
                flatten_all_positions,
                "fetch_live_quote",
                return_value={"data_unavailable": True, "reason": "sandbox 404"},
            ),
        ):
            exit_code = _run(["--confirm", "--reason", "test emergency"])

        assert exit_code == 1
        mock_executor.exit_trade.assert_not_called()


class TestBrokerOnlyPositionCrossCheck:
    """REAL-MONEY-READINESS FIX (2026-09-07 audit): flatten_all_positions.py used to decide
    "nothing to flatten" purely from algo_trades - exactly wrong for a tool whose entire
    purpose is "something is badly wrong", which includes the DB and broker having diverged
    (e.g. circuit_breaker.py deleting an "orphan" algo_positions row for a still-live broker
    position). It must cross-check against the broker's own positions and never silently
    report flat while real exposure remains."""

    def test_status_reports_untracked_broker_position(self, capsys):
        with (
            patch.object(flatten_all_positions, "_fetch_open_trades", return_value=[]),
            patch.object(flatten_all_positions, "AlgoConfig", return_value={"execution_mode": "paper"}),
            patch.object(flatten_all_positions, "HaltFlagManager") as mock_halt_cls,
        ):
            exit_code = _run(["--status"], broker_only=[("ORPHAN", 10.0)])

        assert exit_code == 0
        mock_halt_cls.assert_not_called()
        out = capsys.readouterr().out
        assert "UNTRACKED broker-only positions" in out
        assert "ORPHAN" in out

    def test_untracked_broker_position_is_not_a_noop(self, capsys):
        """The core bug: DB empty + broker has a real position must NOT report 'nothing to
        flatten' - it must be flagged and closed."""
        mock_halt_manager = MagicMock()
        mock_halt_manager.set_halt_flag.return_value = True
        mock_executor = MagicMock()

        with (
            patch.object(flatten_all_positions, "_fetch_open_trades", return_value=[]),
            patch.object(flatten_all_positions, "AlgoConfig", return_value={"execution_mode": "paper"}),
            patch.object(flatten_all_positions, "HaltFlagManager", return_value=mock_halt_manager),
            patch.object(flatten_all_positions, "TradeExecutor", return_value=mock_executor),
            patch.object(
                flatten_all_positions,
                "_close_untracked_broker_position",
                return_value={"success": True, "message": "closed"},
            ),
        ):
            exit_code = _run(["--confirm", "--reason", "test emergency"], broker_only=[("ORPHAN", 10.0)])

        out = capsys.readouterr().out
        assert "nothing to flatten" not in out.lower()
        assert exit_code == 0
        assert "ORPHAN" in out
        mock_halt_manager.set_halt_flag.assert_called_once()

    def test_untracked_broker_position_close_failure_is_reported(self, capsys):
        mock_halt_manager = MagicMock()
        mock_halt_manager.set_halt_flag.return_value = True
        mock_executor = MagicMock()

        with (
            patch.object(flatten_all_positions, "_fetch_open_trades", return_value=[]),
            patch.object(flatten_all_positions, "AlgoConfig", return_value={"execution_mode": "paper"}),
            patch.object(flatten_all_positions, "HaltFlagManager", return_value=mock_halt_manager),
            patch.object(flatten_all_positions, "TradeExecutor", return_value=mock_executor),
            patch.object(
                flatten_all_positions,
                "_close_untracked_broker_position",
                return_value={"success": False, "message": "broker rejected close"},
            ),
        ):
            exit_code = _run(["--confirm", "--reason", "test emergency"], broker_only=[("ORPHAN", 10.0)])

        assert exit_code == 1
        out = capsys.readouterr().out
        assert "broker rejected close" in out

    def test_broker_fetch_failure_fails_closed_not_silent(self, capsys):
        """If we can't reach the broker to verify, never fall back to trusting DB-only state
        (which is exactly the failure mode this fix closes)."""
        with (
            patch.object(flatten_all_positions, "_fetch_open_trades", return_value=[]),
            patch.object(flatten_all_positions, "AlgoConfig", return_value={"execution_mode": "paper"}),
            patch.object(
                flatten_all_positions, "_fetch_broker_only_symbols", side_effect=ValueError("broker auth failed")
            ),
        ):
            with patch.object(sys, "argv", ["flatten_all_positions.py", "--status"]):
                exit_code = flatten_all_positions.main()

        assert exit_code == 1
        err = capsys.readouterr().err
        assert "Could not verify against broker" in err


class TestUnfilledOrderCancellation:
    """2026-09-06 real-money-readiness audit finding: PENDING/OPEN trades have no filled
    position yet, so routing them through exit_trade() always failed with "Position quantity
    unavailable" while leaving the resting broker order live - it could fill minutes later
    with no bracket/stop protection attached, right after an operator believed the account
    was flat. These must be cancelled at the broker instead of routed through exit_trade.

    2026-09-10 real-money-readiness audit FOLLOW-UP: cancelling by symbol
    (cancel_all_open_orders_for_symbol) is unsafe here - per that function's own docstring
    it's only safe once a position is confirmed CLOSED, and pyramiding means an
    already-FILLED sibling position's live protective stop can rest at the broker for the
    same symbol as this still-unfilled entry. Cancellation must be scoped to this trade's
    own alpaca_order_id (cancel_bracket_orders), and a fill-vs-cancel race (the entry
    actually filled before the cancel landed) must be recovered by closing the resulting
    position immediately, never silently reported as "cancelled"."""

    def test_open_status_trade_cancels_by_order_id_not_by_symbol(self, capsys):
        mock_halt_manager = MagicMock()
        mock_halt_manager.set_halt_flag.return_value = True
        mock_executor = MagicMock()
        mock_executor.order_manager.cancel_bracket_orders.return_value = {
            "success": True,
            "message": "Order cancelled",
            "filled_qty": None,
            "filled_avg_price": None,
        }

        with (
            patch.object(flatten_all_positions, "_fetch_open_trades", return_value=[(1, "AAPL", "open", "ord-a")]),
            patch.object(flatten_all_positions, "HaltFlagManager", return_value=mock_halt_manager),
            patch.object(flatten_all_positions, "AlgoConfig", return_value={"execution_mode": "paper"}),
            patch.object(flatten_all_positions, "TradeExecutor", return_value=mock_executor),
        ):
            exit_code = _run(["--confirm", "--reason", "test emergency"])

        assert exit_code == 0
        mock_executor.exit_trade.assert_not_called()
        mock_executor.order_manager.cancel_bracket_orders.assert_called_once_with("ord-a")
        mock_executor.order_manager.cancel_all_open_orders_for_symbol.assert_not_called()
        out = capsys.readouterr().out
        assert "1 closed, 0 failed" in out

    def test_pending_status_trade_also_routed_to_cancellation(self):
        mock_halt_manager = MagicMock()
        mock_halt_manager.set_halt_flag.return_value = True
        mock_executor = MagicMock()
        mock_executor.order_manager.cancel_bracket_orders.return_value = {
            "success": True,
            "message": "Order cancelled",
            "filled_qty": None,
            "filled_avg_price": None,
        }

        with (
            patch.object(flatten_all_positions, "_fetch_open_trades", return_value=[(2, "MSFT", "pending", "ord-m")]),
            patch.object(flatten_all_positions, "HaltFlagManager", return_value=mock_halt_manager),
            patch.object(flatten_all_positions, "AlgoConfig", return_value={"execution_mode": "paper"}),
            patch.object(flatten_all_positions, "TradeExecutor", return_value=mock_executor),
        ):
            exit_code = _run(["--confirm", "--reason", "test emergency"])

        assert exit_code == 0
        mock_executor.exit_trade.assert_not_called()
        mock_executor.order_manager.cancel_bracket_orders.assert_called_once_with("ord-m")

    def test_cancel_failure_for_unfilled_order_reported_and_nonzero_exit(self, capsys):
        mock_halt_manager = MagicMock()
        mock_halt_manager.set_halt_flag.return_value = True
        mock_executor = MagicMock()
        mock_executor.order_manager.cancel_bracket_orders.return_value = {
            "success": False,
            "message": "Could not cancel order ord-a: timeout",
            "filled_qty": None,
            "filled_avg_price": None,
        }

        with (
            patch.object(flatten_all_positions, "_fetch_open_trades", return_value=[(1, "AAPL", "open", "ord-a")]),
            patch.object(flatten_all_positions, "HaltFlagManager", return_value=mock_halt_manager),
            patch.object(flatten_all_positions, "AlgoConfig", return_value={"execution_mode": "paper"}),
            patch.object(flatten_all_positions, "TradeExecutor", return_value=mock_executor),
        ):
            exit_code = _run(["--confirm", "--reason", "test emergency"])

        assert exit_code == 1
        out = capsys.readouterr().out
        assert "timeout" in out

    def test_missing_alpaca_order_id_fails_safe_without_calling_broker(self, capsys):
        """A PENDING/OPEN trade with no alpaca_order_id on file must never fall back to a
        symbol-wide cancel (the unsafe pre-fix behavior) - fail closed and surface it."""
        mock_halt_manager = MagicMock()
        mock_halt_manager.set_halt_flag.return_value = True
        mock_executor = MagicMock()

        with (
            patch.object(flatten_all_positions, "_fetch_open_trades", return_value=[(1, "AAPL", "open", None)]),
            patch.object(flatten_all_positions, "HaltFlagManager", return_value=mock_halt_manager),
            patch.object(flatten_all_positions, "AlgoConfig", return_value={"execution_mode": "paper"}),
            patch.object(flatten_all_positions, "TradeExecutor", return_value=mock_executor),
        ):
            exit_code = _run(["--confirm", "--reason", "test emergency"])

        assert exit_code == 1
        mock_executor.order_manager.cancel_bracket_orders.assert_not_called()
        mock_executor.order_manager.cancel_all_open_orders_for_symbol.assert_not_called()
        out = capsys.readouterr().out
        assert "no alpaca_order_id on file" in out

    def test_fill_vs_cancel_race_closes_the_new_fill_instead_of_reporting_cancelled(self, capsys):
        """The entry actually filled during the cancel attempt - must not be silently
        reported as 'cancelled' while a real, unprotected position sits at the broker."""
        mock_halt_manager = MagicMock()
        mock_halt_manager.set_halt_flag.return_value = True
        mock_executor = MagicMock()
        mock_executor.order_manager.cancel_bracket_orders.return_value = {
            "success": False,
            "message": "order already filled",
            "filled_qty": 10.0,
            "filled_avg_price": 150.0,
        }

        with (
            patch.object(flatten_all_positions, "_fetch_open_trades", return_value=[(1, "AAPL", "open", "ord-a")]),
            patch.object(flatten_all_positions, "HaltFlagManager", return_value=mock_halt_manager),
            patch.object(flatten_all_positions, "AlgoConfig", return_value={"execution_mode": "auto"}),
            patch.object(flatten_all_positions, "TradeExecutor", return_value=mock_executor),
            patch.object(
                flatten_all_positions,
                "_close_untracked_broker_position",
                return_value={"success": True, "message": "closed via broker"},
            ) as mock_close,
        ):
            exit_code = _run(["--confirm", "--reason", "test emergency"])

        assert exit_code == 0
        mock_executor.exit_trade.assert_not_called()
        mock_close.assert_called_once()
        assert mock_close.call_args.args[1] == "AAPL"
        out = capsys.readouterr().out
        assert "RACE-FILLED then CLOSED AAPL" in out

    def test_fill_vs_cancel_race_close_failure_is_reported_needs_manual_attention(self, capsys):
        mock_halt_manager = MagicMock()
        mock_halt_manager.set_halt_flag.return_value = True
        mock_executor = MagicMock()
        mock_executor.order_manager.cancel_bracket_orders.return_value = {
            "success": False,
            "message": "order already filled",
            "filled_qty": 10.0,
            "filled_avg_price": 150.0,
        }

        with (
            patch.object(flatten_all_positions, "_fetch_open_trades", return_value=[(1, "AAPL", "open", "ord-a")]),
            patch.object(flatten_all_positions, "HaltFlagManager", return_value=mock_halt_manager),
            patch.object(flatten_all_positions, "AlgoConfig", return_value={"execution_mode": "auto"}),
            patch.object(flatten_all_positions, "TradeExecutor", return_value=mock_executor),
            patch.object(
                flatten_all_positions,
                "_close_untracked_broker_position",
                return_value={"success": False, "message": "broker rejected close"},
            ),
        ):
            exit_code = _run(["--confirm", "--reason", "test emergency"])

        assert exit_code == 1
        out = capsys.readouterr().out
        assert "NEEDS MANUAL ATTENTION" in out

    def test_mixed_unfilled_and_filled_trades_both_handled(self):
        mock_halt_manager = MagicMock()
        mock_halt_manager.set_halt_flag.return_value = True
        mock_executor = MagicMock()
        mock_executor.order_manager.cancel_bracket_orders.return_value = {
            "success": True,
            "message": "Order cancelled",
            "filled_qty": None,
            "filled_avg_price": None,
        }
        mock_executor.exit_trade.return_value = {"success": True}

        with (
            patch.object(
                flatten_all_positions,
                "_fetch_open_trades",
                return_value=[(1, "AAPL", "open", "ord-a"), (2, "MSFT", "filled", "ord-m")],
            ),
            patch.object(flatten_all_positions, "HaltFlagManager", return_value=mock_halt_manager),
            patch.object(flatten_all_positions, "AlgoConfig", return_value={"execution_mode": "paper"}),
            patch.object(flatten_all_positions, "TradeExecutor", return_value=mock_executor),
            patch.object(flatten_all_positions, "fetch_live_quote", return_value=150.0),
        ):
            exit_code = _run(["--confirm", "--reason", "test emergency"])

        assert exit_code == 0
        mock_executor.order_manager.cancel_bracket_orders.assert_called_once_with("ord-a")
        mock_executor.exit_trade.assert_called_once()
        assert mock_executor.exit_trade.call_args.kwargs["trade_id"] == 2


class TestPostFlattenVerification:
    """REAL-MONEY-READINESS FIX (2026-09-10 /goal pre-live-money audit): every step above
    trusts its OWN success signal - none of that proves the account is actually flat at the
    broker afterward. Re-query /v2/positions one more time at the end and treat any
    remaining position as a failure regardless of what every step above believed."""

    def test_verification_confirms_flat_when_broker_reports_nothing(self, capsys):
        mock_halt_manager = MagicMock()
        mock_halt_manager.set_halt_flag.return_value = True
        mock_executor = MagicMock()
        mock_executor.exit_trade.return_value = {"success": True}

        with (
            patch.object(flatten_all_positions, "_fetch_open_trades", return_value=[(1, "AAPL", "filled", "ord-a")]),
            patch.object(flatten_all_positions, "HaltFlagManager", return_value=mock_halt_manager),
            patch.object(flatten_all_positions, "AlgoConfig", return_value={"execution_mode": "paper"}),
            patch.object(flatten_all_positions, "TradeExecutor", return_value=mock_executor),
            patch.object(flatten_all_positions, "fetch_live_quote", return_value=150.0),
        ):
            exit_code = _run(["--confirm", "--reason", "test emergency"], remaining_after_flatten=[])

        assert exit_code == 0
        assert "broker confirms zero open positions" in capsys.readouterr().out

    def test_verification_catches_a_position_every_step_believed_was_closed(self, capsys):
        """The core case this fix exists for: every per-symbol step reports success, but the
        broker still shows a live position - must be surfaced as a failure, not missed."""
        mock_halt_manager = MagicMock()
        mock_halt_manager.set_halt_flag.return_value = True
        mock_executor = MagicMock()
        mock_executor.exit_trade.return_value = {"success": True}

        with (
            patch.object(flatten_all_positions, "_fetch_open_trades", return_value=[(1, "AAPL", "filled", "ord-a")]),
            patch.object(flatten_all_positions, "HaltFlagManager", return_value=mock_halt_manager),
            patch.object(flatten_all_positions, "AlgoConfig", return_value={"execution_mode": "paper"}),
            patch.object(flatten_all_positions, "TradeExecutor", return_value=mock_executor),
            patch.object(flatten_all_positions, "fetch_live_quote", return_value=150.0),
        ):
            exit_code = _run(
                ["--confirm", "--reason", "test emergency"],
                remaining_after_flatten=[{"symbol": "AAPL", "qty": 5.0}],
            )

        assert exit_code == 1
        err = capsys.readouterr().err
        assert "POST-FLATTEN VERIFICATION FAILED" in err
        assert "AAPL" in err

    def test_zero_qty_broker_rows_are_not_treated_as_still_open(self):
        mock_halt_manager = MagicMock()
        mock_halt_manager.set_halt_flag.return_value = True
        mock_executor = MagicMock()
        mock_executor.exit_trade.return_value = {"success": True}

        with (
            patch.object(flatten_all_positions, "_fetch_open_trades", return_value=[(1, "AAPL", "filled", "ord-a")]),
            patch.object(flatten_all_positions, "HaltFlagManager", return_value=mock_halt_manager),
            patch.object(flatten_all_positions, "AlgoConfig", return_value={"execution_mode": "paper"}),
            patch.object(flatten_all_positions, "TradeExecutor", return_value=mock_executor),
            patch.object(flatten_all_positions, "fetch_live_quote", return_value=150.0),
        ):
            exit_code = _run(
                ["--confirm", "--reason", "test emergency"],
                remaining_after_flatten=[{"symbol": "AAPL", "qty": 0.0}],
            )

        assert exit_code == 0

    def test_verification_fetch_failure_warns_but_does_not_mask_other_failures(self, capsys):
        mock_halt_manager = MagicMock()
        mock_halt_manager.set_halt_flag.return_value = True
        mock_executor = MagicMock()
        mock_executor.exit_trade.return_value = {"success": False, "message": "broker rejected order"}

        with (
            patch.object(flatten_all_positions, "_fetch_open_trades", return_value=[(1, "AAPL", "filled", "ord-a")]),
            patch.object(flatten_all_positions, "HaltFlagManager", return_value=mock_halt_manager),
            patch.object(flatten_all_positions, "AlgoConfig", return_value={"execution_mode": "paper"}),
            patch.object(flatten_all_positions, "TradeExecutor", return_value=mock_executor),
            patch.object(flatten_all_positions, "fetch_live_quote", return_value=150.0),
            patch.object(sys, "argv", ["flatten_all_positions.py", "--confirm", "--reason", "test emergency"]),
            patch.object(flatten_all_positions, "_fetch_broker_only_symbols", return_value=[]),
            patch.object(flatten_all_positions, "_fetch_broker_positions", side_effect=RuntimeError("network down")),
        ):
            exit_code = flatten_all_positions.main()

        assert exit_code == 1
        err = capsys.readouterr().err
        assert "Could not verify the account is actually flat" in err
        assert "broker rejected order" in err
