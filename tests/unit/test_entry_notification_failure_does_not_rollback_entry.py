#!/usr/bin/env python3
"""Regression test for a live-money-risk bug in EntryHandler._send_entry_notification.

_send_entry_notification is PHASE 4 of _execute_entry_txn, called after PHASE 2 (order
submission - in auto mode, a REAL Alpaca buy that has already filled) and PHASE 3 (the
algo_trades/algo_positions INSERT, in the SAME transaction/cursor). The pre-fix code
re-raised on any notification failure under a "FAIL-FAST, must not proceed with the
trade" rationale - but that rationale only holds if the check runs BEFORE the trade
happens. By PHASE 4 there is nothing left to prevent: the trade already happened.
Re-raising propagated out of _execute_entry_txn, out of the `with DatabaseContext
("write") as cur:` block in _with_cursor, which rolls back on any exception - deleting
the just-inserted algo_trades/algo_positions rows for a position that was already
bought for real at the broker. Result: a fully real, broker-held position with ZERO
record anywhere in the DB - invisible to every stop-loss, risk check, circuit breaker,
and exit path. Mirrors the identical fix in ExitHandler._execute_exit (see
test_exit_notification_failure_does_not_rollback_exit.py).

Static source check rather than a full mocked call: _execute_entry_txn has a large
dependency graph that would need extensive mocking to exercise end-to-end (see
test_exit_handler_clears_pending_client_order_id.py for the same rationale).
"""

import re
from pathlib import Path

SOURCE = (Path(__file__).parent.parent.parent / "algo" / "trading" / "executor_entry_handler.py").read_text()


def _send_entry_notification_body() -> str:
    match = re.search(
        r"def _send_entry_notification\(.*?\n(.*?)\Z",
        SOURCE,
        re.DOTALL,
    )
    assert match, "could not locate _send_entry_notification in executor_entry_handler.py"
    return match.group(1)


def test_entry_notification_failure_does_not_raise():
    """A notification delivery problem must never revert an already-committed,
    already-broker-filled entry - the except block must not re-raise."""
    body = _send_entry_notification_body()
    except_pos = body.index("except Exception as e:")
    handler_body = body[except_pos:]
    assert "raise" not in handler_body, (
        f"entry notification exception handler must not re-raise - doing so propagates "
        f"out of _execute_entry_txn's DatabaseContext('write') block and rolls back an "
        f"already-committed, already-broker-filled entry, leaving a real position with "
        f"zero DB record anywhere. Handler body:\n{handler_body}"
    )


def test_notify_entry_phase_runs_inside_the_transaction_after_the_order_and_record_phases():
    """Sanity check the premise: PHASE 4 (notify) must run after PHASE 2 (submit) and
    PHASE 3 (record) inside the same _execute_entry_txn - if this ordering changes, the
    non-blocking requirement above should be re-examined."""
    match = re.search(
        r"def _execute_entry_txn\(.*?\n(.*?)\n        # Execute entry transaction with locks", SOURCE, re.DOTALL
    )
    assert match, "could not locate _execute_entry_txn"
    txn_body = match.group(1)
    submit_pos = txn_body.index("_submit_entry_phase")
    record_pos = txn_body.index("_record_entry_phase")
    notify_pos = txn_body.index("_notify_entry_phase")
    assert submit_pos < record_pos < notify_pos, (
        "expected order submission, then DB record, then notify - if this changed, "
        "re-evaluate whether notification failure can still be made non-blocking safely"
    )
