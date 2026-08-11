"""Regression test for a 2026-08-10 live bug: ExitHandler.execute_exit() accepted a
price_is_estimated parameter but never forwarded it to _execute_exit(), whose own
signature didn't even declare it. _execute_exit() referenced the bare name
`price_is_estimated` in its body (to decide whether a paper/auto-mode fill price needs
later reconciliation) - since the name was never in scope, this was a guaranteed
NameError the first time any real exit executed. It went undetected because every local
orchestrator run that day had 0 exits, so _execute_exit() was never actually invoked.

Caught via `ruff check --select F821` (undefined-name), not via test coverage - this file
closes that coverage gap by asserting the parameter actually reaches _execute_exit() on
both call paths (cur provided vs. cur=None, which routes through a lambda closure).
"""

from unittest.mock import MagicMock

from algo.trading.executor_exit_handler import ExitHandler


def _make_handler():
    context = MagicMock()
    context._with_cursor = lambda fn, acquire_locks=True: fn(MagicMock())
    return ExitHandler(context)


def test_price_is_estimated_forwarded_with_explicit_cursor():
    handler = _make_handler()
    handler._execute_exit = MagicMock(return_value={"success": True})

    handler.execute_exit(
        trade_id=1,
        exit_price=10.0,
        exit_reason="test",
        exit_fraction=1.0,
        cur=MagicMock(),
        price_is_estimated=True,
    )

    args, _kwargs = handler._execute_exit.call_args
    assert args[-1] is True, "price_is_estimated=True must reach _execute_exit's last positional arg"


def test_price_is_estimated_forwarded_without_explicit_cursor():
    handler = _make_handler()
    handler._execute_exit = MagicMock(return_value={"success": True})

    handler.execute_exit(
        trade_id=1,
        exit_price=10.0,
        exit_reason="test",
        exit_fraction=1.0,
        cur=None,
        price_is_estimated=True,
    )

    args, _kwargs = handler._execute_exit.call_args
    assert args[-1] is True, "cur=None path (lambda closure) must also forward price_is_estimated"


def test_price_is_estimated_defaults_to_false():
    handler = _make_handler()
    handler._execute_exit = MagicMock(return_value={"success": True})

    handler.execute_exit(
        trade_id=1,
        exit_price=10.0,
        exit_reason="test",
        exit_fraction=1.0,
        cur=MagicMock(),
    )

    args, _kwargs = handler._execute_exit.call_args
    assert args[-1] is False
