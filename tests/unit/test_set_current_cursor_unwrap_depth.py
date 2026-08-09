"""Regression test: set_current_cursor()'s wrapper-unwrap loop
(lambda/api/routes/utils.py) used `while hasattr(current, "cursor")` with no depth
bound. For a real psycopg2 cursor this terminates fine (real cursors have no `.cursor`
attribute), but for anything where `.cursor` keeps returning an object that itself
satisfies `hasattr(x, "cursor")` - e.g. a bare `unittest.mock.MagicMock` used as a fake
cursor in tests, which auto-creates ANY attribute access including `.cursor` and
`.description` on every child - the loop never terminates. Live-confirmed: this hung
tests/unit/test_circuit_breaker_panel_drawdown_threshold.py (and, transitively, any
route handler wrapped by the `wrapper` decorator that calls set_current_cursor with a
MagicMock cursor) indefinitely - which is why a full `pytest tests/unit` run never
completed. A malformed/self-wrapping real wrapper in production would hit the identical
failure mode, hanging the request.

Fixed by bounding the unwrap loop to 10 iterations.
"""

import importlib
from unittest.mock import MagicMock

# 'lambda' is a Python keyword, so the module under test is loaded via importlib
# rather than a normal `from lambda...` import.
_utils_module = importlib.import_module("lambda.api.routes.utils")
_thread_local = _utils_module._thread_local
set_current_cursor = _utils_module.set_current_cursor


class _RealCursorLike:
    """No `.cursor` attribute - mirrors an actual psycopg2 cursor. Loop must stop here."""

    description = ("col1",)


def test_unwraps_real_two_level_wrapper_chain_to_the_actual_cursor():
    """Uses the actual production wrapper classes, not hand-rolled fixtures - both
    _ErrorLoggedCursor and _CorrelationIdCursor expose `.description` as a property that
    forwards down the chain (see utils/db/context.py), so a naive fixture without that
    forwarding doesn't reproduce the real unwrap path."""
    db_context = importlib.import_module("utils.db.context")

    real_cursor = _RealCursorLike()
    inner_wrapper = db_context._ErrorLoggedCursor(real_cursor)
    outer_wrapper = db_context._CorrelationIdCursor(inner_wrapper, correlation_id="test-123")

    set_current_cursor(outer_wrapper)

    assert _thread_local.cursor is real_cursor


def test_passthrough_when_no_cursor_attribute():
    bare = _RealCursorLike()

    set_current_cursor(bare)

    assert _thread_local.cursor is bare


def test_does_not_hang_on_self_perpetuating_mock_cursor():
    """The actual bug: a MagicMock's `.cursor` and `.description` both auto-resolve to
    truthy child mocks forever, so naive `hasattr` unwrapping never finds a base case.
    This must return promptly (bounded loop), not hang."""
    fake_cursor = MagicMock()

    set_current_cursor(fake_cursor)  # must return - test times out via pytest if it hangs

    # Some unwrapped mock is stored; the important assertion is that we got here at all.
    assert _thread_local.cursor is not None
