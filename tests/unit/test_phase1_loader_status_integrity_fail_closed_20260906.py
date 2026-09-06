"""Regression test: verify_loader_status_completion_integrity() used to fail OPEN on a DB
error during its own check - logging a warning and returning None ("no integrity problem
found, continue") - reintroducing exactly the "just logging" gap its own CRITICAL FIX
2026-08-02 docstring says was already fixed for the main comparison logic (Session 344's
"100% complete but 1 symbol loaded" corruption). Real-money-readiness audit, 2026-09-06:
fixed to fail closed (halt) instead.
"""

from unittest.mock import MagicMock

import psycopg2

from algo.orchestrator.phase1_price_freshness import verify_loader_status_completion_integrity


def test_db_error_halts_instead_of_silently_continuing():
    cur = MagicMock()
    cur.execute.side_effect = psycopg2.OperationalError("connection lost")

    result = verify_loader_status_completion_integrity(cur, lambda *a: None)

    assert result is not None, "must halt (not return None) when integrity can't be verified"
    assert result.halted is True
    assert result.status == "halted"


def test_no_status_row_is_a_clean_pass():
    cur = MagicMock()
    cur.fetchone.return_value = None
    result = verify_loader_status_completion_integrity(cur, lambda *a: None)
    assert result is None


def test_consistent_completion_pct_is_a_clean_pass():
    cur = MagicMock()
    cur.fetchone.return_value = (99.0, 4900, 5000)  # reported vs actual roughly consistent
    result = verify_loader_status_completion_integrity(cur, lambda *a: None)
    assert result is None


def test_actual_corruption_still_halts_as_before():
    cur = MagicMock()
    cur.fetchone.return_value = (100.0, 1, 5000)  # reports 100% but only 1/5000 actually loaded
    result = verify_loader_status_completion_integrity(cur, lambda *a: None)
    assert result is not None
    assert result.halted is True
