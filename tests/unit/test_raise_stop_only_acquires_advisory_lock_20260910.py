"""Regression test: ExitHandler._raise_stop_only's cur=None branch must acquire the
algo_positions advisory lock, matching its sibling execute_exit's cur=None branch.

REAL-MONEY-READINESS FINDING (2026-09-10, pyramiding/sector-cap re-audit): execute_exit's
own cur=None branch passes acquire_locks=True (executor_exit_handler.py's execute_exit,
~line 131) when it opens its own cursor - but _raise_stop_only's cur=None branch called
context._with_cursor(_raise_stop) with no acquire_locks argument, defaulting to False
(executor.py's _with_cursor: `acquire_locks: bool = False`). Not currently live-exploitable
- the only production caller (exit_engine.py, exit_fraction=0) always supplies its own cur
from a SERIALIZABLE transaction already holding FOR UPDATE OF p on the position row - but a
future caller invoking _raise_stop_only/execute_exit(exit_fraction=0) without its own cur
would read/write algo_positions.current_stop_price with zero advisory-lock protection
against a concurrent writer, the same race class phase6_exit_execution.py's broker-stop-
sync-staleness fix closed for its own two write sites earlier this session.
"""

from unittest.mock import MagicMock

from algo.trading.executor_exit_handler import ExitHandler


def test_raise_stop_only_with_no_cursor_acquires_advisory_lock():
    handler_context = MagicMock()
    handler_context._with_cursor.return_value = {"success": True}
    handler = ExitHandler(handler_context)

    handler._raise_stop_only(trade_id=1, new_stop_price=105.0, cur=None)

    handler_context._with_cursor.assert_called_once()
    _, kwargs = handler_context._with_cursor.call_args
    assert kwargs.get("acquire_locks") is True, (
        "_raise_stop_only's cur=None branch must pass acquire_locks=True to _with_cursor - "
        "matching execute_exit's own cur=None branch - so a future caller without its own "
        "cursor/transaction protection isn't left racing a concurrent stop-price writer"
    )


def test_raise_stop_only_with_caller_supplied_cursor_does_not_reacquire_lock():
    """When the caller already supplies a cursor (exit_engine.py's normal path, already
    inside its own SERIALIZABLE transaction with FOR UPDATE OF p), _raise_stop_only must not
    call _with_cursor at all - it uses the caller's cursor directly."""
    handler_context = MagicMock()
    handler = ExitHandler(handler_context)
    fake_cursor = MagicMock()
    fake_cursor.fetchone.return_value = (100.0, "order-1", 10, None, 42)
    handler_context._sync_bracket_stop_loss.return_value = {"success": True}

    handler._raise_stop_only(trade_id=1, new_stop_price=105.0, cur=fake_cursor)

    handler_context._with_cursor.assert_not_called()
