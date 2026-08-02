"""Regression coverage for algo/orchestrator/phase1_data_freshness.py's
_check_health_column_coverage(), extracted from run() after commit c6862e04a.

That commit fixed a live incident: a missing put_call_ratio (an optional 8pt
sentiment enrichment algo/risk/market_exposure.py already skips gracefully)
raised a RuntimeError that halted Phase 1 and cascaded to skip Phase 2 (circuit
breakers), Phase 4 (reconciliation), Phase 5 (exposure policy), and Phase 7
(signal generation) entirely - for a field that was explicitly made optional
2.5 hours earlier the same day. The fix itself shipped with no unit test; this
file closes that gap so the specific halt-vs-warn decisions have direct
coverage instead of relying on live reproduction to catch a regression.
"""

import logging
from datetime import date

import pytest

from algo.orchestrator.phase1_data_freshness import _check_health_column_coverage

_LOGGER_NAME = "algo.orchestrator.phase1_data_freshness"


class TestHealthColumnCoverage:
    def test_missing_put_call_ratio_warns_not_halts(self, caplog) -> None:
        """The exact regression from commit c6862e04a: total_rows present,
        pcr_rows=0 (put_call_ratio null for every row that day) must log a
        warning and return normally, never raise."""
        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            _check_health_column_coverage(
                total_rows=10, pcr_rows=0, pcr_distinct=None, vix_rows=10, vix_distinct=5, health_max_date=date(2026, 7, 27)
            )
        assert any("put_call_ratio" in r.message and r.levelname == "WARNING" for r in caplog.records)

    def test_missing_vix_warns_not_halts(self, caplog) -> None:
        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            _check_health_column_coverage(
                total_rows=10, pcr_rows=10, pcr_distinct=5, vix_rows=0, vix_distinct=None, health_max_date=date(2026, 7, 27)
            )
        assert any("VIX" in r.message and r.levelname == "WARNING" for r in caplog.records)

    def test_both_optional_columns_missing_warns_twice_not_halts(self, caplog) -> None:
        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            _check_health_column_coverage(
                total_rows=10, pcr_rows=0, pcr_distinct=None, vix_rows=0, vix_distinct=None, health_max_date=date(2026, 7, 27)
            )
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 2

    def test_no_rows_at_all_still_halts(self) -> None:
        """total_rows=0 means the whole market_health_daily row is missing for
        that date - a genuinely critical gap, distinct from an optional column
        being null within an existing row. This must still raise."""
        with pytest.raises(RuntimeError, match="market_health_daily has no rows"):
            _check_health_column_coverage(
                total_rows=0, pcr_rows=0, pcr_distinct=None, vix_rows=0, vix_distinct=None, health_max_date=date(2026, 7, 27)
            )

    def test_full_coverage_logs_no_warnings(self, caplog) -> None:
        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            _check_health_column_coverage(
                total_rows=10, pcr_rows=10, pcr_distinct=5, vix_rows=10, vix_distinct=8, health_max_date=date(2026, 7, 27)
            )
        assert not any(r.levelname == "WARNING" for r in caplog.records)
