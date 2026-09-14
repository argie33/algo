"""Regression test for PatrolLogger.log_results (algo/monitoring/data_patrol/logger.py).

Added 2026-09-13 (goal session: patrol/quarantine comprehensiveness). apply_symbol_quarantine
used to only be invoked for a check_name when that run's result was error/critical with a
non-empty flagged_symbols list - so once a symbol was quarantined, there was no path back to
resolved_at ever being set once the underlying issue was fixed and the check started passing
clean (INFO/no flagged_symbols) again. Live-confirmed 2026-09-13: check_ohlc_sanity's own query
returned zero live violations, yet 15 symbols from an earlier dirty run were still open in
symbol_quarantine.
"""

from unittest.mock import MagicMock, patch

from algo.monitoring.data_patrol.base import CheckResult
from algo.monitoring.data_patrol.config import INFO
from algo.monitoring.data_patrol.logger import PatrolLogger


def test_clean_result_still_calls_apply_symbol_quarantine_to_resolve_stale_rows() -> None:
    cur = MagicMock()
    finding = CheckResult(
        check_name="ohlc_sanity",
        severity=INFO,
        target_table="price_daily",
        message="OHLC relationships valid",
    )
    with patch("algo.monitoring.data_patrol.logger.apply_symbol_quarantine") as mock_apply:
        PatrolLogger("run-1").log_results(cur, [finding])

    mock_apply.assert_called_once_with(cur, "ohlc_sanity", INFO, "run-1", [])


def test_error_result_with_no_flagged_symbols_still_resolves_but_does_not_insert() -> None:
    cur = MagicMock()
    finding = CheckResult(
        check_name="some_check",
        severity="error",
        target_table="price_daily",
        message="something failed generically, no per-symbol attribution",
    )
    with patch("algo.monitoring.data_patrol.logger.apply_symbol_quarantine") as mock_apply:
        PatrolLogger("run-2").log_results(cur, [finding])

    mock_apply.assert_called_once_with(cur, "some_check", "error", "run-2", [])


def test_error_result_with_flagged_symbols_still_inserts() -> None:
    cur = MagicMock()
    finding = CheckResult(
        check_name="ohlc_sanity",
        severity="error",
        target_table="price_daily",
        message="OHLC violation",
        details={"flagged_symbols": [{"symbol": "ARTL", "reason": "high < open/close/low"}]},
    )
    with patch("algo.monitoring.data_patrol.logger.apply_symbol_quarantine") as mock_apply:
        PatrolLogger("run-3").log_results(cur, [finding])

    mock_apply.assert_called_once_with(
        cur, "ohlc_sanity", "error", "run-3", [{"symbol": "ARTL", "reason": "high < open/close/low"}]
    )
