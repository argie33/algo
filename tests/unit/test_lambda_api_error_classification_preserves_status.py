"""Regression tests: handle_db_error/raise_db_error must preserve the real
status code of a deliberately-raised APIException.

lambda/api/exceptions.py's APIException hierarchy (BadRequest, Forbidden,
NotFound, Conflict, ...) is entirely separate from utils.exceptions.core's
BaseAPIError, which is the only hierarchy utils.error_handlers.classify_exception
recognizes. Many route handlers wrap their own logic in a broad
`except Exception: handle_db_error(...)` / `except Exception: raise_db_error(...)`
(lambda/api/routes/positions.py, trades.py, and likely others) - this catches
their OWN deliberately-raised raise_api_error() calls (e.g. a validation 400,
an admin-check 403, a not-found 404) before those exceptions can ever reach the
real error-boundary middleware documented in exceptions.py's own docstring.
Pre-fix, classify_exception's isinstance(error, BaseAPIError) check silently
failed for every one of these, and handle_db_error/raise_db_error fell back to
a generic 500/503 - discarding the correct status code and the real message.

'lambda' is a Python keyword, so the modules under test are loaded via
importlib rather than a normal `from lambda...` import.
"""

import importlib

import pytest

routes_utils = importlib.import_module("lambda.api.routes.utils")

# lambda/api/routes/utils.py imports its exception classes via a bare `from
# exceptions import (...)`, which only resolves correctly once lambda/api/ is on
# sys.path (done by importing routes_utils itself, transitively via its own
# `import setup_imports`). Grabbing the classes back off routes_utils - rather
# than a fresh `importlib.import_module("lambda.api.exceptions")` - is required:
# that dotted import registers a SEPARATE module under a different sys.modules
# key, producing a second, non-isinstance-compatible APIException class even
# though it's the same source file.
BadRequest = routes_utils.BadRequest
Forbidden = routes_utils.Forbidden
NotFound = routes_utils.NotFound
ServiceUnavailable = routes_utils.ServiceUnavailable


def test_handle_db_error_preserves_bad_request_status_code():
    err = BadRequest("stop_loss_price must be below entry_price", error_type="bad_request")
    status_code, error_type, message = routes_utils.handle_db_error(err, "test context")
    assert status_code == 400
    assert error_type == "bad_request"
    assert "stop_loss_price" in message


def test_handle_db_error_preserves_forbidden_status_code():
    err = Forbidden("Admin access required", error_type="forbidden")
    status_code, error_type, message = routes_utils.handle_db_error(err, "test context")
    assert status_code == 403
    assert error_type == "forbidden"


def test_handle_db_error_preserves_not_found_status_code():
    err = NotFound("Position 42 not found", error_type="not_found")
    status_code, error_type, message = routes_utils.handle_db_error(err, "test context")
    assert status_code == 404
    assert error_type == "not_found"


def test_raise_db_error_reraises_api_exception_unchanged():
    err = BadRequest("bad input", error_type="bad_request")
    with pytest.raises(BadRequest) as exc_info:
        routes_utils.raise_db_error(err, "test context")
    assert exc_info.value.status_code == 400


def test_raise_db_error_still_maps_real_db_errors_to_503():
    """Non-APIException errors (real DB failures) keep the prior 503/504 behavior."""
    with pytest.raises(ServiceUnavailable):
        routes_utils.raise_db_error(RuntimeError("connection reset"), "test context")
