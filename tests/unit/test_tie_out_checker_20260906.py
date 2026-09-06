"""Regression tests for TieOutChecker (algo/monitoring/data_patrol/checks/tie_out.py).

Added 2026-09-06 (same /goal session that wired the checker into DataPatrol). Covers the three
identities (balance sheet, cash flow, EPS) and the latest-real-fiscal-year dedup that keeps each
check to one row per symbol instead of re-flagging every historical year forever.
"""

from unittest.mock import MagicMock

from algo.monitoring.data_patrol.checks.tie_out import TieOutChecker
from algo.monitoring.data_patrol.config import PatrolConfig


def _checker() -> TieOutChecker:
    return TieOutChecker(PatrolConfig())


def _mock_cursor(fetchall_results: list[list[dict]]) -> MagicMock:
    """Cursor whose .fetchall() returns each list in order, one call per .execute()."""
    cur = MagicMock()
    cur.fetchall.side_effect = fetchall_results
    return cur


class TestBalanceSheetIdentity:
    def test_flags_row_beyond_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "BADCO",
                        "fiscal_year": 2025,
                        "total_assets": 1000.0,
                        "total_liabilities": 400.0,
                        "stockholders_equity": 400.0,  # off by 200, 20% of assets
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_balance_sheet_identity(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "balance_sheet_identity"
        assert checker.results[0].details["count"] == 1
        assert checker.results[0].details["examples"][0]["symbol"] == "BADCO"

    def test_does_not_flag_within_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "GOODCO",
                        "fiscal_year": 2025,
                        "total_assets": 1000.0,
                        "total_liabilities": 600.0,
                        "stockholders_equity": 400.0,  # exact tie-out
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_balance_sheet_identity(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year_per_symbol(self) -> None:
        """The SQL itself must select DISTINCT ON (symbol) ordered by fiscal_year DESC -
        this is what keeps a stale old-year mismatch from re-flagging forever once a symbol's
        current data ties out cleanly."""
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_balance_sheet_identity(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (b.symbol)" in executed_sql
        assert "ORDER BY b.symbol, b.fiscal_year DESC" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_balance_sheet_identity(cur)  # must not raise
        assert checker.results == []


class TestCashflowReconciliation:
    def test_does_not_flag_residual_under_floor(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "BADCF",
                        "fiscal_year": 2025,
                        "operating_cash_flow": 100.0,
                        "investing_cash_flow": -50.0,
                        "financing_cash_flow": -10.0,
                        "prior_cash": 1000.0,
                        "curr_cash": 1000.0,  # implied 1040 vs actual 1000 = $40 residual
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_cashflow_reconciliation(cur)
        # $40 residual is under the $1M floor - must NOT flag despite being a real mismatch,
        # since the floor exists to suppress rounding/immateriality noise.
        assert checker.results == []

    def test_flags_row_beyond_floor(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "BADCF2",
                        "fiscal_year": 2025,
                        "operating_cash_flow": 100_000_000.0,
                        "investing_cash_flow": -50_000_000.0,
                        "financing_cash_flow": -10_000_000.0,
                        "prior_cash": 1_000_000_000.0,
                        "curr_cash": 900_000_000.0,  # implied 1.04B vs actual 900M = $140M residual
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_cashflow_reconciliation(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "cashflow_reconciliation"

    def test_query_excludes_depository_institutions(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_cashflow_reconciliation(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "company_info_sec" in executed_sql
        assert "sic_code = ANY" in executed_sql
        params = cur.execute.call_args[0][1]
        assert 6022 in params[0]  # state commercial banks SIC code present in exclusion list

    def test_query_dedups_cash_flow_cte_to_latest_fiscal_year(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_cashflow_reconciliation(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (symbol)" in executed_sql
        assert "ORDER BY symbol, fiscal_year DESC" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_cashflow_reconciliation(cur)  # must not raise
        assert checker.results == []


class TestEpsReconciliation:
    def test_flags_unit_scale_mismatch(self) -> None:
        """This is the real bug class this check exists to catch - a shares_outstanding_diluted
        magnitude error (e.g. millions vs. raw units) that survives every other check silently."""
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "BADSHARES",
                        "fiscal_year": 2025,
                        "net_income": 2_000_000_000.0,
                        "diluted_eps": 1.0,
                        "shares_outstanding_diluted": 3_000_000_000_000.0,  # off by ~1000x
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_eps_reconciliation(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "eps_reconciliation"
        assert checker.results[0].details["examples"][0]["symbol"] == "BADSHARES"

    def test_does_not_flag_within_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "GOODEPS",
                        "fiscal_year": 2025,
                        "net_income": 1_000_000_000.0,
                        "diluted_eps": 2.0,
                        "shares_outstanding_diluted": 500_000_000.0,  # exact tie-out
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_eps_reconciliation(cur)
        assert checker.results == []

    def test_query_excludes_zero_denominators_and_dedups(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_eps_reconciliation(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "shares_outstanding_diluted != 0" in executed_sql
        assert "net_income != 0" in executed_sql
        assert "DISTINCT ON (i.symbol)" in executed_sql
        assert "ORDER BY i.symbol, i.fiscal_year DESC" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_eps_reconciliation(cur)  # must not raise
        assert checker.results == []


class TestGrossProfitIdentity:
    def test_flags_row_beyond_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "BADGP",
                        "fiscal_year": 2025,
                        "revenue": 1_000_000_000.0,
                        "cost_of_revenue": 600_000_000.0,
                        "gross_profit": 100_000_000.0,  # implied 400M vs tagged 100M
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_gross_profit_identity(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "gross_profit_identity"

    def test_does_not_flag_within_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "GOODGP",
                        "fiscal_year": 2025,
                        "revenue": 1_000_000_000.0,
                        "cost_of_revenue": 600_000_000.0,
                        "gross_profit": 400_000_000.0,  # exact tie-out
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_gross_profit_identity(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_gross_profit_identity(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (i.symbol)" in executed_sql
        assert "ORDER BY i.symbol, i.fiscal_year DESC" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_gross_profit_identity(cur)  # must not raise
        assert checker.results == []


class TestPretaxToNetIncome:
    def test_flags_row_beyond_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "BADTAX",
                        "fiscal_year": 2025,
                        "pretax_income": 1_000_000_000.0,
                        "income_tax_expense": 200_000_000.0,
                        "net_income": 2_000_000_000.0,  # implied 800M vs tagged 2B
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_pretax_to_net_income(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "pretax_to_net_income"

    def test_does_not_flag_within_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "GOODTAX",
                        "fiscal_year": 2025,
                        "pretax_income": 1_000_000_000.0,
                        "income_tax_expense": 200_000_000.0,
                        "net_income": 800_000_000.0,  # exact tie-out
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_pretax_to_net_income(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_pretax_to_net_income(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (i.symbol)" in executed_sql
        assert "ORDER BY i.symbol, i.fiscal_year DESC" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_pretax_to_net_income(cur)  # must not raise
        assert checker.results == []


class TestRunAggregatesAllChecks:
    def test_run_calls_all_five_checks(self) -> None:
        cur = _mock_cursor([[], [], [], [], []])
        checker = _checker()
        results = checker.run(cur)
        assert results == []
        assert cur.execute.call_count == 5
