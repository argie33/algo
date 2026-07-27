#!/usr/bin/env python3
"""Regression test: Phase 9's algo_positions_with_risk view-refresh step must only
treat a permission-denied error as an expected, non-critical condition when actually
running in LOCAL_MODE.

Previously the InsufficientPrivilege handler downgraded to a warning unconditionally,
with no LOCAL_MODE check at all - so a real production misconfiguration (the DB role
losing REFRESH privilege on the view, e.g. after a credential rotation or a migration
applied under the wrong role) would silently log a warning and continue forever,
leaving the positions/risk dashboard serving stale data with no critical alert ever
firing. Fixed to only treat it as expected when LOCAL_MODE is actually set, and raise
RuntimeError (matching the handling of every other DB error on this refresh) otherwise.
"""

import os
from unittest.mock import MagicMock, patch

import psycopg2

from algo.orchestrator.phase9_reconciliation import _refresh_positions_with_risk_view


def _mock_ctx_raising(exc):
    mock_cur = MagicMock()
    mock_cur.execute.side_effect = exc
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False
    return mock_ctx


def test_insufficient_privilege_outside_local_mode_raises_critical():
    """A permission-denied error in a non-LOCAL_MODE environment (production) must
    raise, not be silently downgraded to a warning - this is the pre-fix bug."""
    exc = psycopg2.errors.InsufficientPrivilege("permission denied for materialized view algo_positions_with_risk")
    mock_ctx = _mock_ctx_raising(exc)
    log_calls = []

    env = dict(os.environ)
    env.pop("LOCAL_MODE", None)
    with patch.dict(os.environ, env, clear=True):
        with patch("algo.orchestrator.phase9_reconciliation.DatabaseContext", return_value=mock_ctx):
            try:
                _refresh_positions_with_risk_view(lambda *args: log_calls.append(args))
                raised = False
            except RuntimeError:
                raised = True

    assert raised, "expected InsufficientPrivilege outside LOCAL_MODE to raise RuntimeError, not warn-and-continue"
    assert not any(call[2] == "warning" for call in log_calls), (
        "must not log a soft warning for a production permission failure"
    )


def test_insufficient_privilege_in_local_mode_warns_and_continues():
    """The graceful, non-critical downgrade must still work when LOCAL_MODE is actually set."""
    exc = psycopg2.errors.InsufficientPrivilege("permission denied for materialized view algo_positions_with_risk")
    mock_ctx = _mock_ctx_raising(exc)
    log_calls = []

    with patch.dict(os.environ, {"LOCAL_MODE": "true"}):
        with patch("algo.orchestrator.phase9_reconciliation.DatabaseContext", return_value=mock_ctx):
            _refresh_positions_with_risk_view(lambda *args: log_calls.append(args))

    assert log_calls and log_calls[0][:3] == (9, "positions_view_refresh", "warning")


def test_successful_refresh_logs_success():
    mock_cur = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False
    log_calls = []

    with patch("algo.orchestrator.phase9_reconciliation.DatabaseContext", return_value=mock_ctx):
        _refresh_positions_with_risk_view(lambda *args: log_calls.append(args))

    assert mock_cur.execute.call_args_list[0].args[0] == "REFRESH MATERIALIZED VIEW algo_positions_with_risk"
    assert log_calls and log_calls[0][:3] == (9, "positions_view_refresh", "success")
