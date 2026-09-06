"""Regression test: validate_portfolio_symbol_prices() used to fail OPEN on a DB/data error
during its own check - logging a warning and returning None ("no problem found, continue")
- exactly the failure mode this check exists to prevent (Phase 6 halting mid-run trying to
exit a position with no price data, the original "5 errors" pattern it was built to catch
early). Real-money-readiness audit, 2026-09-06: fixed to fail closed (halt) instead.
"""

from unittest.mock import MagicMock

import psycopg2
import pytest

from algo.orchestrator.phase1_readiness_checks import validate_portfolio_symbol_prices


def _cur_raising(exc):
    cur = MagicMock()
    cur.execute.side_effect = exc
    return cur


@pytest.mark.parametrize(
    "exc",
    [
        psycopg2.OperationalError("connection lost"),
        psycopg2.DatabaseError("db error"),
        ValueError("bad data"),
        KeyError("missing"),
        TypeError("wrong type"),
    ],
)
def test_error_during_check_halts_instead_of_silently_continuing(exc):
    cur = _cur_raising(exc)
    log_calls = []
    result = validate_portfolio_symbol_prices(cur, {}, lambda *a: log_calls.append(a))

    assert result is not None, "must halt (not return None) when coverage can't be verified"
    assert result.halted is True
    assert result.status == "halted"


def test_no_open_positions_is_a_clean_pass():
    cur = MagicMock()
    cur.fetchall.return_value = []
    result = validate_portfolio_symbol_prices(cur, {}, lambda *a: None)
    assert result is None


def test_missing_prices_still_halts_as_before():
    cur = MagicMock()
    cur.fetchall.side_effect = [[("AAPL",)], []]  # portfolio symbols, then no matching prices
    result = validate_portfolio_symbol_prices(cur, {}, lambda *a: None)
    assert result is not None
    assert result.halted is True
