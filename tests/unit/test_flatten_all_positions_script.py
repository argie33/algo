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


def _run(argv):
    with patch.object(sys, "argv", ["flatten_all_positions.py", *argv]):
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
            return_value=[(1, "AAPL", "filled"), (2, "MSFT", "filled")],
        ):
            with patch.object(flatten_all_positions, "HaltFlagManager") as mock_halt_cls:
                exit_code = _run(["--status"])

        assert exit_code == 0
        mock_halt_cls.assert_not_called()
        out = capsys.readouterr().out
        assert "AAPL" in out and "MSFT" in out
        assert "Open positions: 2" in out


class TestFlattenFlow:
    def test_no_open_positions_is_a_noop(self, capsys):
        with patch.object(flatten_all_positions, "_fetch_open_trades", return_value=[]):
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
            patch.object(flatten_all_positions, "_fetch_open_trades", return_value=[(1, "AAPL", "filled")]),
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
            patch.object(flatten_all_positions, "_fetch_open_trades", return_value=[(1, "AAPL", "filled")]),
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
                return_value=[(1, "AAPL", "filled"), (2, "MSFT", "filled")],
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
            patch.object(flatten_all_positions, "_fetch_open_trades", return_value=[(1, "AAPL", "filled")]),
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
                return_value=[(1, "AAPL", "filled"), (2, "MSFT", "filled")],
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
            patch.object(flatten_all_positions, "_fetch_open_trades", return_value=[(1, "AAPL", "filled")]),
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
            patch.object(flatten_all_positions, "_fetch_open_trades", return_value=[(1, "AAPL", "filled")]),
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


class TestUnfilledOrderCancellation:
    """2026-09-06 real-money-readiness audit finding: PENDING/OPEN trades have no filled
    position yet, so routing them through exit_trade() always failed with "Position quantity
    unavailable" while leaving the resting broker order live - it could fill minutes later
    with no bracket/stop protection attached, right after an operator believed the account
    was flat. These must be cancelled at the broker instead of routed through exit_trade."""

    def test_open_status_trade_cancels_broker_order_not_exit_trade(self, capsys):
        mock_halt_manager = MagicMock()
        mock_halt_manager.set_halt_flag.return_value = True
        mock_executor = MagicMock()
        mock_executor.order_manager.cancel_all_open_orders_for_symbol.return_value = {
            "success": True,
            "cancelled_order_ids": ["ord-1"],
            "message": "Cancelled 1 stale order(s) for AAPL",
        }

        with (
            patch.object(flatten_all_positions, "_fetch_open_trades", return_value=[(1, "AAPL", "open")]),
            patch.object(flatten_all_positions, "HaltFlagManager", return_value=mock_halt_manager),
            patch.object(flatten_all_positions, "AlgoConfig", return_value={"execution_mode": "paper"}),
            patch.object(flatten_all_positions, "TradeExecutor", return_value=mock_executor),
        ):
            exit_code = _run(["--confirm", "--reason", "test emergency"])

        assert exit_code == 0
        mock_executor.exit_trade.assert_not_called()
        mock_executor.order_manager.cancel_all_open_orders_for_symbol.assert_called_once_with("AAPL")
        out = capsys.readouterr().out
        assert "1 closed, 0 failed" in out

    def test_pending_status_trade_also_routed_to_cancellation(self):
        mock_halt_manager = MagicMock()
        mock_halt_manager.set_halt_flag.return_value = True
        mock_executor = MagicMock()
        mock_executor.order_manager.cancel_all_open_orders_for_symbol.return_value = {
            "success": True,
            "cancelled_order_ids": [],
            "message": "No open orders for MSFT",
        }

        with (
            patch.object(flatten_all_positions, "_fetch_open_trades", return_value=[(2, "MSFT", "pending")]),
            patch.object(flatten_all_positions, "HaltFlagManager", return_value=mock_halt_manager),
            patch.object(flatten_all_positions, "AlgoConfig", return_value={"execution_mode": "paper"}),
            patch.object(flatten_all_positions, "TradeExecutor", return_value=mock_executor),
        ):
            exit_code = _run(["--confirm", "--reason", "test emergency"])

        assert exit_code == 0
        mock_executor.exit_trade.assert_not_called()
        mock_executor.order_manager.cancel_all_open_orders_for_symbol.assert_called_once_with("MSFT")

    def test_cancel_failure_for_unfilled_order_reported_and_nonzero_exit(self, capsys):
        mock_halt_manager = MagicMock()
        mock_halt_manager.set_halt_flag.return_value = True
        mock_executor = MagicMock()
        mock_executor.order_manager.cancel_all_open_orders_for_symbol.return_value = {
            "success": False,
            "cancelled_order_ids": [],
            "message": "Could not list open orders for AAPL: timeout",
        }

        with (
            patch.object(flatten_all_positions, "_fetch_open_trades", return_value=[(1, "AAPL", "open")]),
            patch.object(flatten_all_positions, "HaltFlagManager", return_value=mock_halt_manager),
            patch.object(flatten_all_positions, "AlgoConfig", return_value={"execution_mode": "paper"}),
            patch.object(flatten_all_positions, "TradeExecutor", return_value=mock_executor),
        ):
            exit_code = _run(["--confirm", "--reason", "test emergency"])

        assert exit_code == 1
        out = capsys.readouterr().out
        assert "timeout" in out

    def test_mixed_unfilled_and_filled_trades_both_handled(self):
        mock_halt_manager = MagicMock()
        mock_halt_manager.set_halt_flag.return_value = True
        mock_executor = MagicMock()
        mock_executor.order_manager.cancel_all_open_orders_for_symbol.return_value = {
            "success": True,
            "cancelled_order_ids": ["ord-1"],
            "message": "Cancelled 1 stale order(s) for AAPL",
        }
        mock_executor.exit_trade.return_value = {"success": True}

        with (
            patch.object(
                flatten_all_positions,
                "_fetch_open_trades",
                return_value=[(1, "AAPL", "open"), (2, "MSFT", "filled")],
            ),
            patch.object(flatten_all_positions, "HaltFlagManager", return_value=mock_halt_manager),
            patch.object(flatten_all_positions, "AlgoConfig", return_value={"execution_mode": "paper"}),
            patch.object(flatten_all_positions, "TradeExecutor", return_value=mock_executor),
            patch.object(flatten_all_positions, "fetch_live_quote", return_value=150.0),
        ):
            exit_code = _run(["--confirm", "--reason", "test emergency"])

        assert exit_code == 0
        mock_executor.order_manager.cancel_all_open_orders_for_symbol.assert_called_once_with("AAPL")
        mock_executor.exit_trade.assert_called_once()
        assert mock_executor.exit_trade.call_args.kwargs["trade_id"] == 2
