"""Regression test for a fail-open exception in EntryHandler.execute_entry()'s position-dedup
check (algo/trading/executor_entry_handler.py, "POSITION DEDUP" block).

The block exists specifically to prevent creating two separate algo_positions rows for the
same symbol on the same day (its own comment: "Reuse it instead of creating duplicate
positions"). Unlike its two sibling duplicate checks earlier in the same function
(check_duplicate_position, check_idempotent_duplicate - both correctly `raise` DatabaseError
on failure, which TradeExecutor's caller already catches and converts into a clean blocked
result), this block used to catch a bare `Exception`, log it, and silently fall through -
leaving `position_id` at its pre-check value (None), identical to the "confirmed no
duplicate" path. A transient DB failure here was indistinguishable from "genuinely no
duplicate exists" and proceeded to generate a brand-new position_id.

`algo_positions` has no DB-level unique constraint on symbol (only on the randomly-generated
position_id, which can never collide) - this in-code check is the ONLY thing preventing two
open positions for the same symbol on the same day if the same entry gets processed twice
(e.g. a retried orchestrator run after a transient failure).

Fixed to re-raise, matching the two sibling checks' fail-closed behavior. TradeExecutor's
enter_trade() wrapper already catches DatabaseError/Exception from this exact call and
converts it into a clean {"success": False, "status": "database_error", ...} result - the
raise is caught one level up, not left to propagate uncaught.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from algo.trading.executor_entry_handler import EntryHandler


def _make_context():
    ctx = MagicMock()
    ctx.symbol = "TESTSYM"
    ctx.prices.entry_price = Decimal("100.00")
    ctx.prices.stop_loss_price = Decimal("95.00")
    ctx.prices.target_1_price = Decimal("110.00")
    ctx.prices.target_2_price = None
    ctx.prices.target_3_price = None
    ctx.shares = Decimal("10")
    ctx.signal_date = date(2026, 8, 10)
    ctx.entry_date = date(2026, 8, 10)
    return ctx


def _make_handler():
    handler_context = MagicMock()
    handler_context.execution_mode = "paper"
    handler_context._get_portfolio_value.return_value = Decimal("100000")
    handler_context.validator.validate_entry_preconditions.return_value = (True, "", {})
    handler_context.validator.check_duplicate_position.return_value = (False, "")
    handler_context.validator.check_idempotent_duplicate.return_value = (False, "", None)

    def _with_cursor(fn):
        return fn(MagicMock())

    handler_context._with_cursor.side_effect = _with_cursor
    return EntryHandler(handler_context)


class TestPositionDedupFailsClosed:
    def test_db_failure_during_dedup_check_raises_not_silently_proceeds(self):
        handler = _make_handler()
        context = _make_context()

        with patch(
            "utils.db.context.DatabaseContext",
            side_effect=RuntimeError("simulated DB connectivity blip"),
        ):
            with pytest.raises(RuntimeError, match="simulated DB connectivity blip"):
                handler.execute_entry(context)
