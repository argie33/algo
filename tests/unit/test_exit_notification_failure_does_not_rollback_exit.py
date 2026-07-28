#!/usr/bin/env python3
"""Regression test for a live-money-risk bug in ExitHandler._execute_exit()'s post-exit
notification block.

By the time that block runs, the exit is already fully committed on this transaction's
cursor (algo_trades/algo_positions/algo_audit_log all updated) and, in auto mode, a real
broker sell order has already filled - an irreversible, already-happened event. The
pre-fix code caught `NotificationError` and re-raised as `RuntimeError`, despite its own
comment reading "non-blocking failure". That except clause could never even match:
TradeNotificationService._send_notification/_save_notification raise bare RuntimeError
(DB write failure) or whatever exception AlertManager._send_email raises (e.g. SMTP
errors) - never NotificationError. So any notification hiccup propagated uncaught out of
_execute_exit, out of the `with DatabaseContext("write") as cur:` block in
executor.py's _with_cursor, which rolls back the entire transaction on any exception -
undoing the already-real broker exit's DB record. execute_exit()'s own outer
`except Exception` then swallowed that RuntimeError into a plain `success: False` return,
so no crash and no halted status ever signaled the problem - just a position that was
really closed at the broker but silently reverted to "open" in the DB.

Static source check rather than a full mocked call: _execute_exit has a large dependency
graph (guards, lock/fetch, bracket cancellation, order submission, position update) that
would need extensive mocking to exercise end-to-end (see
test_exit_handler_clears_pending_client_order_id.py for the same rationale).
"""

import re
from pathlib import Path

SOURCE = (Path(__file__).parent.parent.parent / "algo" / "trading" / "executor_exit_handler.py").read_text()


def _notification_block() -> str:
    match = re.search(
        r"# Send notification.*?\n(.*?)\n\n        return \{",
        SOURCE,
        re.DOTALL,
    )
    assert match, "could not locate the post-exit notification block in executor_exit_handler.py"
    return match.group(1)


def test_notification_block_catches_broadly_not_a_narrow_dead_type():
    """The except clause must catch Exception (or another type that _send_notification
    actually raises), not NotificationError - which _send_notification never raises,
    making a narrower except clause dead code that lets everything else through."""
    block = _notification_block()
    assert "except Exception as notif_e:" in block, (
        "notification failure handling must catch broadly (Exception) - "
        "TradeNotificationService._send_notification/_save_notification never raise "
        "NotificationError, so `except NotificationError` here is dead code that lets "
        "the real exception type propagate and roll back an already-completed exit"
    )


def test_notification_failure_does_not_raise():
    """The except block must not re-raise (directly or via a bare `raise` / wrapping
    RuntimeError) - a notification delivery problem must never roll back a real,
    already-committed/already-broker-filled exit."""
    block = _notification_block()
    except_pos = block.index("except Exception as notif_e:")
    handler_body = block[except_pos:]
    assert "raise" not in handler_body, (
        f"notification exception handler must not re-raise - doing so propagates out of "
        f"the exit's DatabaseContext('write') block and rolls back an already-completed, "
        f"already-broker-filled exit. Handler body:\n{handler_body}"
    )
