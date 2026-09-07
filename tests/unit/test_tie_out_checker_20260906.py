"""Regression tests for TieOutChecker (algo/monitoring/data_patrol/checks/tie_out.py).

Added 2026-09-06 (same /goal session that wired the checker into DataPatrol). Covers the three
identities (balance sheet, cash flow, EPS) and the latest-real-fiscal-year dedup that keeps each
check to one row per symbol instead of re-flagging every historical year forever.
"""

from unittest.mock import MagicMock

from algo.monitoring.data_patrol.checks.tie_out import TieOutChecker
from algo.monitoring.data_patrol.config import ERROR, PatrolConfig


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
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "balance_sheet_identity"
        assert checker.results[0].severity == ERROR


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

    def test_query_excludes_individually_verified_embedded_fintech_symbols(self) -> None:
        """MELI/AXP/CRCL have the same structural embedded-fintech-float cash-flow mismatch as
        the SIC-coded exchanges/broker-dealers but their own SIC codes (7389, 6199) are too
        generic to exclude wholesale - see _CASHFLOW_INTERMEDIARY_SYMBOL_ALLOWLIST's comment."""
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_cashflow_reconciliation(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "cf.symbol = ANY(%s)" in executed_sql
        params = cur.execute.call_args[0][1]
        assert set(params[1]) == {"MELI", "AXP", "CRCL"}

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
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "cashflow_reconciliation"
        assert checker.results[0].severity == ERROR


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
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "eps_reconciliation"
        assert checker.results[0].severity == ERROR


class TestBasicEpsReconciliation:
    """Mirrors TestEpsReconciliation above, but for check_basic_eps_reconciliation
    (eps * shares_outstanding_basic ~= net_income) - added 2026-09-07, same day as the
    check itself, because the diluted pair had monitoring-layer tie-out coverage while the
    basic pair had none at all."""

    def test_flags_unit_scale_mismatch(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "BADSHARES",
                        "fiscal_year": 2025,
                        "net_income": 2_000_000_000.0,
                        "earnings_per_share": 1.0,
                        "shares_outstanding_basic": 3_000_000_000_000.0,  # off by ~1000x
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_basic_eps_reconciliation(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "basic_eps_reconciliation"
        assert checker.results[0].details["examples"][0]["symbol"] == "BADSHARES"

    def test_does_not_flag_within_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "GOODEPS",
                        "fiscal_year": 2025,
                        "net_income": 1_000_000_000.0,
                        "earnings_per_share": 2.0,
                        "shares_outstanding_basic": 500_000_000.0,  # exact tie-out
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_basic_eps_reconciliation(cur)
        assert checker.results == []

    def test_query_excludes_zero_denominators_and_dedups(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_basic_eps_reconciliation(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "shares_outstanding_basic != 0" in executed_sql
        assert "net_income != 0" in executed_sql
        assert "DISTINCT ON (i.symbol)" in executed_sql
        assert "ORDER BY i.symbol, i.fiscal_year DESC" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_basic_eps_reconciliation(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "basic_eps_reconciliation"
        assert checker.results[0].severity == ERROR


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
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "gross_profit_identity"
        assert checker.results[0].severity == ERROR


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
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "pretax_to_net_income"
        assert checker.results[0].severity == ERROR


class TestDilutedGeBasicShares:
    def test_flags_diluted_below_basic(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "BADSH",
                        "fiscal_year": 2025,
                        "shares_outstanding_basic": 100_000_000.0,
                        "shares_outstanding_diluted": 90_000_000.0,  # diluted < basic
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_diluted_ge_basic_shares(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "diluted_ge_basic_shares"

    def test_does_not_flag_equal_counts(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "GOODSH",
                        "fiscal_year": 2025,
                        "shares_outstanding_basic": 100_000_000.0,
                        "shares_outstanding_diluted": 100_000_000.0,  # no dilutive securities
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_diluted_ge_basic_shares(cur)
        assert checker.results == []

    def test_does_not_flag_diluted_above_basic(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "OKSH",
                        "fiscal_year": 2025,
                        "shares_outstanding_basic": 100_000_000.0,
                        "shares_outstanding_diluted": 105_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_diluted_ge_basic_shares(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_diluted_ge_basic_shares(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (i.symbol)" in executed_sql
        assert "ORDER BY i.symbol, i.fiscal_year DESC" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_diluted_ge_basic_shares(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "diluted_ge_basic_shares"
        assert checker.results[0].severity == ERROR


class TestRunAggregatesAllChecks:
    def test_run_calls_all_seven_checks(self) -> None:
        cur = _mock_cursor([[], [], [], [], [], [], []])
        checker = _checker()
        results = checker.run(cur)
        assert results == []
        assert cur.execute.call_count == 7
