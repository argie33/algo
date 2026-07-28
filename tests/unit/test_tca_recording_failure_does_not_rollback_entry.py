#!/usr/bin/env python3
"""Regression test for a live-money-risk bug in EntryHandler._record_tca.

_record_tca runs inside _record_entry_phase, itself inside the same _execute_entry_txn
transaction as the algo_trades/algo_positions INSERT, and is only called when
execution_mode == "auto" after the order has already filled at the broker - an
irreversible, already-happened event. The pre-fix `except DatabaseError` caught
algo.trading.exceptions.DatabaseError, a type self.tca.record_fill() never raises (it
raises bare psycopg2 errors, RuntimeError, or ValueError/TypeError/ZeroDivisionError) -
so every real failure mode propagated uncaught out of this function, out of
_execute_entry_txn, out of _with_cursor's DatabaseContext("write") block, which rolls
back on any exception - deleting the already-inserted trade/position rows for a
position already bought for real at the broker. Same bug class covered by
test_exit_notification_failure_does_not_rollback_exit.py and
test_entry_notification_failure_does_not_rollback_entry.py.

Static source check rather than a full mocked call - see those files for the same
rationale.
"""

import re
from pathlib import Path

SOURCE = (Path(__file__).parent.parent.parent / "algo" / "trading" / "executor_entry_handler.py").read_text()


def _record_tca_body() -> str:
    match = re.search(
        r"def _record_tca\(.*?\n(.*?)\n    def ",
        SOURCE,
        re.DOTALL,
    )
    assert match, "could not locate _record_tca in executor_entry_handler.py"
    return match.group(1)


def test_record_tca_outer_handler_catches_broadly_not_a_narrow_dead_type():
    """The outer except must catch Exception (or the real types record_fill raises),
    not the custom algo.trading.exceptions.DatabaseError - which record_fill never
    raises, making a narrower except clause dead code that lets everything through."""
    body = _record_tca_body()
    assert "except Exception as e:" in body, (
        "TCA recording failure handling must catch broadly (Exception) - "
        "tca.record_fill() never raises algo.trading.exceptions.DatabaseError, so "
        "`except DatabaseError` here was dead code that let the real exception type "
        "propagate and roll back an already-completed, already-broker-filled entry"
    )


def test_record_tca_outer_handler_does_not_raise():
    """The outer except block must not re-raise - a TCA recording problem must never
    roll back an already-committed, already-broker-filled entry."""
    body = _record_tca_body()
    except_pos = body.rindex("except Exception as e:")
    handler_body = body[except_pos:]
    assert "raise" not in handler_body, (
        f"TCA outer exception handler must not re-raise - doing so propagates out of "
        f"the entry's DatabaseContext('write') block and rolls back an already-completed "
        f"entry. Handler body:\n{handler_body}"
    )


def test_tca_slippage_alert_failure_does_not_raise():
    """The inner TCA-alert except (NotificationError) must also not re-raise - a failed
    slippage alert is even more clearly non-critical than the TCA record itself."""
    body = _record_tca_body()
    except_pos = body.index("except NotificationError as e:")
    next_except_pos = body.index("except Exception as e:")
    inner_handler_body = body[except_pos:next_except_pos]
    assert "raise" not in inner_handler_body, (
        f"TCA slippage-alert exception handler must not re-raise. Handler body:\n{inner_handler_body}"
    )
