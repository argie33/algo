"""Regression tests for SpecializedChecker.check_fundamental_data/check_derived_metrics/
check_trade_recorder_columns (algo/monitoring/data_patrol/checks/specialized.py) and
NewXbrlConceptChecker.check_new_concepts (algo/monitoring/data_patrol/checks/xbrl_new_concepts.py)
- 2026-09-08 /goal CI-gap sweep found these four methods had zero pytest coverage despite being
live-wired into their checkers' run().
"""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

from algo.monitoring.data_patrol.checks.specialized import SpecializedChecker
from algo.monitoring.data_patrol.checks.xbrl_new_concepts import NewXbrlConceptChecker
from algo.monitoring.data_patrol.config import ERROR, INFO, WARN, PatrolConfig


def _specialized_checker() -> SpecializedChecker:
    return SpecializedChecker(PatrolConfig())


def _xbrl_checker() -> NewXbrlConceptChecker:
    return NewXbrlConceptChecker(PatrolConfig())


class TestCheckFundamentalData:
    def test_fresh_tables_log_info(self) -> None:
        checker = _specialized_checker()
        cur = MagicMock()
        today_str = date.today().isoformat()
        tables = [
            "quarterly_income_statement",
            "quarterly_balance_sheet",
            "quarterly_cash_flow",
            "annual_income_statement",
            "annual_balance_sheet",
            "annual_cash_flow",
            "sec_valuations",
        ]
        cur.fetchall.return_value = [
            {"tbl_name": tbl, "latest": today_str, "total": 5000, "unique_syms": 500} for tbl in tables
        ]
        checker.check_fundamental_data(cur)
        assert len(checker.results) == len(tables)
        assert all(r.severity == INFO for r in checker.results)

    def test_stale_table_logs_configured_severity(self) -> None:
        checker = _specialized_checker()
        cur = MagicMock()
        tables = [
            "quarterly_income_statement",
            "quarterly_balance_sheet",
            "quarterly_cash_flow",
            "annual_income_statement",
            "annual_balance_sheet",
            "annual_cash_flow",
            "sec_valuations",
        ]
        cur.fetchall.return_value = [
            {"tbl_name": tbl, "latest": "2026-01-01", "total": 5000, "unique_syms": 500} for tbl in tables
        ]
        checker.check_fundamental_data(cur)
        sec_val = next(r for r in checker.results if r.target_table == "sec_valuations")
        assert sec_val.severity == WARN

    def test_empty_table_logs_warn(self) -> None:
        checker = _specialized_checker()
        cur = MagicMock()
        cur.fetchall.return_value = [
            {"tbl_name": "quarterly_income_statement", "latest": None, "total": 0, "unique_syms": 0},
        ]
        checker.check_fundamental_data(cur)
        result = next(r for r in checker.results if r.target_table == "quarterly_income_statement")
        assert result.severity == WARN
        assert "empty" in result.message


class TestCheckDerivedMetrics:
    def test_valid_rsi_and_no_nan_logs_info_twice(self) -> None:
        checker = _specialized_checker()
        cur = MagicMock()
        cur.fetchone.side_effect = [
            {"bad_rsi": 0, "null_rsi": 0, "total": 1000},
            {"bad_atr": 0, "bad_rsi_nan": 0},
        ]
        checker.check_derived_metrics(cur)
        assert len(checker.results) == 2
        assert all(r.severity == INFO for r in checker.results)

    def test_bad_rsi_logs_error(self) -> None:
        checker = _specialized_checker()
        cur = MagicMock()
        cur.fetchone.side_effect = [
            {"bad_rsi": 7, "null_rsi": 0, "total": 1000},
            {"bad_atr": 0, "bad_rsi_nan": 0},
        ]
        checker.check_derived_metrics(cur)
        rsi_result = checker.results[0]
        assert rsi_result.severity == ERROR
        assert rsi_result.details["bad_rsi"] == 7

    def test_nan_values_log_error(self) -> None:
        checker = _specialized_checker()
        cur = MagicMock()
        cur.fetchone.side_effect = [
            {"bad_rsi": 0, "null_rsi": 0, "total": 1000},
            {"bad_atr": 2, "bad_rsi_nan": 1},
        ]
        checker.check_derived_metrics(cur)
        nan_result = checker.results[1]
        assert nan_result.severity == ERROR
        assert nan_result.details["nan_count"] == 3

    def test_query_failure_logs_error_not_raise(self) -> None:
        checker = _specialized_checker()
        cur = MagicMock()
        cur.execute.side_effect = ValueError("bad interval")
        checker.check_derived_metrics(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == ERROR


class TestCheckTradeRecorderColumns:
    def test_valid_structure_and_fresh_data_logs_info(self) -> None:
        checker = _specialized_checker()
        cur = MagicMock()
        trades_cols = [
            {"column_name": c}
            for c in (
                "symbol",
                "entry_date",
                "entry_price",
                "quantity",
                "signal_type",
                "exit_date",
                "exit_price",
                "pnl",
            )
        ]
        positions_cols = [
            {"column_name": c}
            for c in (
                "symbol",
                "entry_date",
                "entry_price",
                "current_price",
                "quantity",
                "status",
                "updated_at",
            )
        ]
        cur.fetchall.side_effect = [trades_cols, positions_cols]
        cur.fetchone.side_effect = [
            {"count": 10, "max_updated": datetime.now(timezone.utc)},
            {"count": 3, "max_updated": datetime.now(timezone.utc)},
        ]
        checker.check_trade_recorder_columns(cur)
        structure_results = [r for r in checker.results if r.check_name == "trade_recorder_columns"]
        assert len(structure_results) == 2
        assert all(r.severity == INFO for r in structure_results)

    def test_missing_column_logs_error(self) -> None:
        checker = _specialized_checker()
        cur = MagicMock()
        cur.fetchall.side_effect = [
            [{"column_name": "symbol"}, {"column_name": "entry_date"}],
            [{"column_name": "symbol"}],
        ]
        checker.check_trade_recorder_columns(cur)
        trades_result = next(r for r in checker.results if r.target_table == "algo_trades")
        assert trades_result.severity == ERROR
        assert "pnl" in trades_result.details["missing"]

    def test_query_failure_logs_warn_not_raise(self) -> None:
        import psycopg2

        checker = _specialized_checker()
        cur = MagicMock()
        cur.execute.side_effect = psycopg2.OperationalError("connection lost")
        checker.check_trade_recorder_columns(cur)
        assert len(checker.results) == 2
        assert all(r.severity == WARN for r in checker.results)


class TestCheckNewConcepts:
    def test_no_cache_on_host_returns_no_findings(self) -> None:
        checker = _xbrl_checker()
        with patch(
            "algo.monitoring.data_patrol.checks.xbrl_new_concepts.iter_companyfacts_cache",
            return_value=[],
        ):
            checker.check_new_concepts()
        assert checker.results == []

    def test_no_gaps_found_returns_no_findings(self) -> None:
        checker = _xbrl_checker()
        with (
            patch(
                "algo.monitoring.data_patrol.checks.xbrl_new_concepts.iter_companyfacts_cache",
                return_value=["AAPL.json"],
            ),
            patch(
                "algo.monitoring.data_patrol.checks.xbrl_new_concepts.find_gaps",
                return_value=[],
            ),
        ):
            checker.check_new_concepts()
        assert len(checker.results) == 1
        assert checker.results[0].severity == INFO

    def test_new_concept_gap_logs_warn(self) -> None:
        checker = _xbrl_checker()
        with (
            patch(
                "algo.monitoring.data_patrol.checks.xbrl_new_concepts.iter_companyfacts_cache",
                return_value=["AAPL.json"],
            ),
            patch(
                "algo.monitoring.data_patrol.checks.xbrl_new_concepts.find_gaps",
                return_value=[(75, "us-gaap:NewConcept", "AAPL")],
            ),
        ):
            checker.check_new_concepts()
        assert len(checker.results) == 1
        assert checker.results[0].severity == WARN
        assert checker.results[0].details["examples"][0]["concept"] == "us-gaap:NewConcept"

    def test_scan_failure_logs_error_not_raise(self) -> None:
        checker = _xbrl_checker()
        with patch(
            "algo.monitoring.data_patrol.checks.xbrl_new_concepts.iter_companyfacts_cache",
            side_effect=RuntimeError("cache directory unreadable"),
        ):
            checker.check_new_concepts()
        assert len(checker.results) == 1
        assert checker.results[0].severity == ERROR
