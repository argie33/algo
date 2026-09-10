"""Regression tests for CoverageChecker.check_loader_contracts/check_signal_quality_ratio
(algo/monitoring/data_patrol/checks/coverage.py) - 2026-09-08 /goal CI-gap sweep found these two
methods (unlike check_universe_coverage/check_loader_coverage in the same class) had zero
pytest coverage despite being live-wired into CoverageChecker.run().
"""

from unittest.mock import MagicMock

from algo.monitoring.data_patrol.checks.coverage import CoverageChecker
from algo.monitoring.data_patrol.config import ERROR, INFO, PatrolConfig


def _checker() -> CoverageChecker:
    return CoverageChecker(PatrolConfig())


class TestCheckLoaderContracts:
    def test_row_count_meets_contract_logs_info(self) -> None:
        checker = _checker()
        checker.config.get_loader_contracts = MagicMock(  # type: ignore[method-assign]
            return_value={
                "price_daily": {
                    "condition": "1=1",
                    "min_rows": 100,
                    "severity": ERROR,
                    "description": "daily prices",
                }
            }
        )
        cur = MagicMock()
        cur.fetchone.return_value = (5000,)
        checker.check_loader_contracts(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == INFO
        assert "OK" in checker.results[0].message

    def test_row_count_below_contract_logs_configured_severity(self) -> None:
        checker = _checker()
        checker.config.get_loader_contracts = MagicMock(  # type: ignore[method-assign]
            return_value={
                "price_daily": {
                    "condition": "1=1",
                    "min_rows": 100000,
                    "severity": ERROR,
                    "description": "daily prices",
                }
            }
        )
        cur = MagicMock()
        cur.fetchone.return_value = (5,)
        checker.check_loader_contracts(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == ERROR
        assert checker.results[0].target_table == "price_daily"

    def test_contract_check_failure_logs_error_and_rolls_back_savepoint(self) -> None:
        checker = _checker()
        checker.config.get_loader_contracts = MagicMock(  # type: ignore[method-assign]
            return_value={
                "price_daily": {
                    "condition": "1=1",
                    "min_rows": 100,
                    "severity": ERROR,
                    "description": "daily prices",
                }
            }
        )
        cur = MagicMock()
        cur.fetchone.side_effect = RuntimeError("relation does not exist")
        checker.check_loader_contracts(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == ERROR
        assert any("ROLLBACK TO SAVEPOINT" in str(call) for call in cur.execute.call_args_list)


class TestCheckSignalQualityRatio:
    def test_clean_signal_ratio_above_threshold_logs_info(self) -> None:
        checker = _checker()
        cur = MagicMock()
        cur.fetchone.return_value = (95, 100)
        checker.check_signal_quality_ratio(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == INFO
        assert "95.0% clean" in checker.results[0].message

    def test_clean_signal_ratio_below_threshold_logs_error(self) -> None:
        checker = _checker()
        cur = MagicMock()
        cur.fetchone.return_value = (50, 100)
        checker.check_signal_quality_ratio(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == ERROR
        assert checker.results[0].details["clean_pct"] == 50.0

    def test_zero_total_rows_skipped_silently(self) -> None:
        checker = _checker()
        cur = MagicMock()
        cur.fetchone.return_value = (0, 0)
        checker.check_signal_quality_ratio(cur)
        assert checker.results == []

    def test_db_error_logged_not_raised(self) -> None:
        import psycopg2

        checker = _checker()
        cur = MagicMock()
        cur.execute.side_effect = psycopg2.OperationalError("connection lost")
        checker.check_signal_quality_ratio(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == ERROR
