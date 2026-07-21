"""Regression test for _WindowsSafeRotatingFileHandler.

logging.handlers.RotatingFileHandler.emit() already wraps its own call to
doRollover() in `except Exception: self.handleError(record)` - which prints the
"--- Logging error ---" traceback to stderr and returns normally. That means an
emit()-level `except PermissionError: pass` override can never actually catch
anything: the exception is consumed inside the parent's emit() before it would
reach a subclass override of emit(). The fix overrides doRollover() instead,
where the PermissionError (Windows: rotate can't rename a file another process
has open) actually originates.
"""

import contextlib
import io
import logging
import os

from dashboard.utilities import _WindowsSafeRotatingFileHandler


def test_rollover_permission_error_does_not_leak_to_stderr(tmp_path) -> None:
    """A PermissionError during rotation (simulating a second process holding
    the rotated-to file open) must be swallowed, not printed as a logging error."""
    log_path = tmp_path / "dashboard-local.log"
    log_path.write_text("x" * 100)

    handler = _WindowsSafeRotatingFileHandler(str(log_path), encoding="utf-8", maxBytes=10, backupCount=3)
    dest = str(log_path) + ".1"

    # Hold the rotation destination open to force a Windows-style PermissionError
    # on rename (simulates a concurrent local dashboard/orchestrator process).
    locked_fd = open(dest, "w")
    try:
        captured = io.StringIO()
        with contextlib.redirect_stderr(captured):
            record = logging.LogRecord("test", logging.INFO, "testmod", 1, "trigger rollover " * 5, None, None)
            handler.emit(record)
        assert "Logging error" not in captured.getvalue()
        assert "PermissionError" not in captured.getvalue()
    finally:
        locked_fd.close()
        handler.close()
        if os.path.exists(dest):
            os.remove(dest)
