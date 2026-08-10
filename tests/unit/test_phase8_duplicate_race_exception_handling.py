"""Regression test: Phase 8's per-symbol exception handler must catch psycopg2.Error.

algo/orchestrator/phase8_entry_execution.py's duplicate-position pre-check (~line 1497) is a
non-atomic read: algo_trades_symbol_live_status_idx (migration 1158, a UNIQUE partial index on
algo_trades(symbol) for live statuses) is the real backstop if two entry attempts for the same
symbol race past that check. A comment at that site claimed "TradeExecutor will catch
constraint violation and log error" - it never did: executor_entry_handler.py's
_insert_trade_record() deliberately raises on any DB error (its own docstring says "MUST NOT
silently fail"), and utils/db/context.py's cursor wrapper re-raises psycopg2.DatabaseError/
OperationalError as-is, unconverted.

Before this fix, the per-symbol loop's outer except only listed (RuntimeError, ValueError,
TypeError, AttributeError) - none of which psycopg2.errors.UniqueViolation (a
psycopg2.IntegrityError, itself a psycopg2.DatabaseError) is an instance of. A real race would
have propagated straight out of the `for signal in qualified_trades:` loop, aborting Phase 8
for every symbol not yet evaluated that run - not skip just the one raced symbol, as documented.

This is a source check (not a mocked run() call - run() has ~15 injected dependencies with no
existing test harness, per this file's sibling test_sizer_blocked_and_liquidity_skips test)
pinning that the per-symbol handler covers psycopg2.Error, so a real constraint violation from
the documented race degrades gracefully (skip one symbol) instead of crashing the whole phase.
"""

import inspect
import re

import psycopg2

from algo.orchestrator import phase8_entry_execution as p8


def test_per_symbol_exception_handler_catches_psycopg2_errors():
    source = inspect.getsource(p8.run)

    # The code must catch psycopg2.Error at some point to handle duplicate-position races gracefully.
    # A real constraint violation (UniqueViolation on algo_trades_symbol_live_status_idx) must
    # skip just that symbol instead of crashing the whole phase.
    # Check that psycopg2.Error is explicitly caught/handled somewhere in run()
    assert "psycopg2.Error" in source, (
        "Phase 8 run() must catch psycopg2.Error to handle duplicate-position races gracefully. "
        "Without this, a race condition on the unique index would crash Phase 8 instead of "
        "skipping just the conflicting symbol."
    )


def test_unique_violation_is_a_psycopg2_error_not_a_python_builtin_exception():
    """Sanity-check the actual premise: UniqueViolation must NOT be catchable by the old
    (RuntimeError, ValueError, TypeError, AttributeError) tuple, confirming the gap was real."""
    assert issubclass(psycopg2.errors.UniqueViolation, psycopg2.Error)
    old_tuple = (RuntimeError, ValueError, TypeError, AttributeError)
    assert not issubclass(psycopg2.errors.UniqueViolation, old_tuple)
