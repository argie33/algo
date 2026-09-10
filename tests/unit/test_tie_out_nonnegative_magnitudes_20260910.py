"""Tests for algo/monitoring/data_patrol/checks/tie_out_nonnegative_magnitudes.py (Round 7,
goal session 2026-09-10: DQC_0015/US1-style "negative values" guard for balance-sheet
magnitude fields that are non-negative by GAAP definition, e.g. total_assets, inventory,
goodwill - a different check class from tie_out.py's existing X<=Y relative bound checks,
which still pass when both sides are wrong-signed together).
"""

from unittest.mock import MagicMock

from algo.monitoring.data_patrol.checks.tie_out import TieOutChecker
from algo.monitoring.data_patrol.config import INFO, WARN, PatrolConfig


def _checker() -> TieOutChecker:
    return TieOutChecker(PatrolConfig())


def _mock_cursor(fetchall_results: list[list[dict]]) -> MagicMock:
    cur = MagicMock()
    cur.fetchall.side_effect = fetchall_results
    return cur


class TestTotalAssetsNonnegative:
    def test_flags_negative_row(self) -> None:
        cur = _mock_cursor([[{"symbol": "BADCO", "fiscal_year": 2025, "total_assets": -500.0}]])
        checker = _checker()
        checker.check_total_assets_nonnegative(cur)
        assert len(checker.results) == 1
        result = checker.results[0]
        assert result.severity == WARN
        assert result.check_name == "total_assets_nonnegative"
        assert result.details["examples"][0]["symbol"] == "BADCO"

    def test_clean_row_logs_info_not_silence(self) -> None:
        # FIXED 2026-09-10 (tie_out_shared.py): a clean run must still log an INFO result so
        # PatrolLogger can supersede/resolve a prior 'open' finding for this check_name -
        # silence here would leave a fixed bug's old WARN row stuck 'open' forever.
        cur = _mock_cursor([[{"symbol": "GOODCO", "fiscal_year": 2025, "total_assets": 500.0}]])
        checker = _checker()
        checker.check_total_assets_nonnegative(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == INFO

    def test_quarterly_variant_uses_quarterly_table_and_columns(self) -> None:
        cur = _mock_cursor([[{"symbol": "BADCO", "fiscal_year": 2025, "fiscal_quarter": "Q2", "total_assets": -500.0}]])
        checker = _checker()
        checker.check_quarterly_total_assets_nonnegative(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "quarterly_balance_sheet" in executed_sql
        assert "b.fiscal_quarter" in executed_sql
        assert checker.results[0].check_name == "quarterly_total_assets_nonnegative"
        assert checker.results[0].details["examples"][0]["fiscal_quarter"] == "Q2"


_EXPECTED_BALANCE_SHEET_FIELDS = [
    "total_assets",
    "current_assets",
    "total_liabilities",
    "current_liabilities",
    "inventory",
    "cash_and_equivalents",
    "accounts_receivable",
    "ppe_net",
    "goodwill",
    "long_term_debt",
    "short_term_debt",
    "operating_lease_liability",
    "finance_lease_liability",
    "accounts_payable",
    "cash_and_restricted_cash_combined",
]


class TestAllFifteenFieldsRegisteredAndDistinctCheckNames:
    def test_run_registers_all_thirty_nonnegative_magnitude_checks(self) -> None:
        # 15 balance-sheet fields x annual/quarterly = 30 distinct check_names, each producing
        # exactly one INFO result on a clean (zero-row) run.
        cur = MagicMock()
        cur.fetchall.return_value = []
        checker = _checker()
        results = checker.run(cur)

        expected_names = {f"{f}_nonnegative" for f in _EXPECTED_BALANCE_SHEET_FIELDS} | {
            f"quarterly_{f}_nonnegative" for f in _EXPECTED_BALANCE_SHEET_FIELDS
        }
        check_names_by_result = {r.check_name: r for r in results}
        assert expected_names <= check_names_by_result.keys()
        assert len(expected_names) == 30
        assert all(check_names_by_result[name].severity == INFO for name in expected_names)

    def test_excludes_net_position_fields_that_can_legitimately_be_negative(self) -> None:
        cur = MagicMock()
        cur.fetchall.return_value = []
        checker = _checker()
        results = checker.run(cur)
        check_names = {r.check_name for r in results}
        for excluded in ("stockholders_equity", "retained_earnings", "noncontrolling_interest", "temporary_equity"):
            assert f"{excluded}_nonnegative" not in check_names
            assert f"quarterly_{excluded}_nonnegative" not in check_names
