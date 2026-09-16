#!/usr/bin/env python3
"""Regression test: a full-exit whose replacement sell order FAILS after this same call
already cancelled the position's protective stop must never let the DB transaction commit
silently.

BUG FOUND 2026-09-10 (pre-live-money /goal audit, order-execution re-audit): when
`full_exit` is True, `cancel_standalone_stop_on_full_exit`/`_cancel_bracket_orders` above
already cancel the broker-side protective stop and null `algo_positions.
standalone_stop_order_id` in the same DB transaction, BEFORE the replacement sell order is
even submitted. If that replacement sell then fails, the old code path just `return`ed a
failure dict - a plain return does not roll back the transaction (only a raised exception
does, per executor.py's `_with_cursor`), so the NULLed stop column would COMMIT alongside a
position that is still live at the broker with no protective stop and status still "open" -
a real naked position with no forced escalation path.

Fixed by raising instead of returning when `full_exit` is True: the DB transaction rolls
back (restoring the OLD standalone_stop_order_id, which Phase 9's is_order_still_live check
will correctly detect no longer matches the broker and auto-remediate), and the CRITICAL
alert uses strict=True with a NotificationError itself forcing a raise - mirroring the
existing bracket-cancel-unconfirmed escalation pattern in this same file.

Static source check, matching the established precedent for this function (see
test_executor_exit_handler_bracket_cancel_race_20260905.py's docstring): _execute_exit has
a large dependency graph impractical to mock end-to-end.
"""

from pathlib import Path

SOURCE = (Path(__file__).parent.parent.parent / "algo" / "trading" / "executor_exit_handler.py").read_text()

_FAILURE_MARKER = "EXIT ORDER FAILED after stop cancelled"


_ANCHOR = 'error_message = "Exit order failed (no error message provided)"'


def _failure_block(source: str, length: int = 5000) -> str:
    assert _FAILURE_MARKER in source, "expected to find the exit-failed-after-stop-cancelled escalation block"
    start = source.index(_ANCHOR)
    return source[start : start + length]


def test_full_exit_failure_after_stop_cancel_raises_instead_of_returning():
    block = _failure_block(SOURCE)
    assert "if full_exit:" in block
    if_idx = block.index("if full_exit:")
    raise_idx = block.index("raise RuntimeError(", if_idx)
    return_idx = block.index("return {", if_idx)
    assert raise_idx < return_idx, (
        "the full_exit branch must raise (forcing a DB rollback) before the generic "
        "return-a-failure-dict path below it, or the transaction commits a naked position"
    )


def test_notify_failure_in_full_exit_branch_also_raises():
    block = _failure_block(SOURCE)
    if_idx = block.index("if full_exit:")
    except_idx = block.index("except NotificationError as e:", if_idx)
    window = block[except_idx : except_idx + 300]
    assert "raise RuntimeError(" in window, (
        "a failed critical alert here must force escalation (raise), unlike the generic "
        "non-full-exit failure path which only logs a warning on notify failure"
    )


def test_full_exit_alert_uses_strict_mode():
    block = _failure_block(SOURCE)
    if_idx = block.index("if full_exit:")
    notify_idx = block.index("notify(", if_idx)
    window = block[notify_idx : notify_idx + 700]
    assert "strict=True" in window
