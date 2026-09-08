#!/usr/bin/env python3
"""Regression tests for scripts/verify_live_trading_readiness.py's
check_paper_trading_track_record() - added 2026-09-07 (real-money-readiness /goal audit) after
finding this script verified every infra precondition (credentials, halt flag, alerts) but
never checked whether the strategy itself currently has real edge. A clean pass on every other
check is meaningless if the live paper track record is, on its own real exit logic, losing
money - this is the gate that catches that instead of relying on a human to notice.
"""

from unittest.mock import MagicMock, patch

from scripts.verify_live_trading_readiness import (
    MIN_PAPER_TRADES,
    check_paper_trading_track_record,
)


def _mock_db(rows):
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = rows
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False
    return patch("utils.db.context.DatabaseContext", return_value=mock_ctx)


def test_negative_expectancy_fails_even_with_plenty_of_trades():
    rows = [(-0.5, "2026-08-01")] * (MIN_PAPER_TRADES + 10)
    with _mock_db(rows):
        failures, _warnings = check_paper_trading_track_record()
    assert len(failures) == 1
    assert "non-positive" in failures[0]


def test_too_few_trades_fails_even_with_positive_expectancy():
    rows = [(1.0, "2026-08-01")] * (MIN_PAPER_TRADES - 1)
    with _mock_db(rows):
        failures, _warnings = check_paper_trading_track_record()
    assert len(failures) == 1
    assert "too small a sample" in failures[0]


def test_positive_expectancy_and_enough_trades_passes():
    rows = [(0.5, "2026-08-01")] * MIN_PAPER_TRADES
    with _mock_db(rows):
        failures, _warnings = check_paper_trading_track_record()
    assert failures == []


def test_zero_closed_trades_fails():
    with _mock_db([]):
        failures, _warnings = check_paper_trading_track_record()
    assert len(failures) == 1
    assert "zero track record" in failures[0]


def test_db_error_reported_as_failure_not_swallowed():
    with patch("utils.db.context.DatabaseContext", side_effect=RuntimeError("connection refused")):
        failures, _warnings = check_paper_trading_track_record()
    assert len(failures) == 1
    assert "connection refused" in failures[0]
