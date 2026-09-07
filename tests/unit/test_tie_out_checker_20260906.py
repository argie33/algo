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
                        "noncontrolling_interest": None,
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
                        "noncontrolling_interest": None,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_balance_sheet_identity(cur)
        assert checker.results == []

    def test_noncontrolling_interest_closes_identity(self) -> None:
        """FIXED 2026-09-07 (migration 1265): a row that would otherwise fail by exactly its
        NCI amount must NOT be flagged once noncontrolling_interest is populated."""
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "XOM",
                        "fiscal_year": 2009,
                        "total_assets": 233_323_000_000.0,
                        "total_liabilities": 117_931_000_000.0,
                        "stockholders_equity": 110_569_000_000.0,
                        "noncontrolling_interest": 4_823_000_000.0,
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


class TestRetainedEarningsRollforward:
    def test_flags_row_beyond_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "BADRE",
                        "fiscal_year": 2025,
                        "prior_retained_earnings": 1_000_000_000.0,
                        "curr_retained_earnings": 1_100_000_000.0,
                        "net_income": 500_000_000.0,  # implied 1.5B vs tagged 1.1B, way off
                        "dividends_paid": None,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_retained_earnings_rollforward(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "retained_earnings_rollforward"

    def test_does_not_flag_within_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "GOODRE",
                        "fiscal_year": 2025,
                        "prior_retained_earnings": 1_000_000_000.0,
                        "curr_retained_earnings": 1_300_000_000.0,
                        "net_income": 500_000_000.0,
                        "dividends_paid": -200_000_000.0,  # exact tie-out: 1B + 500M - 200M = 1.3B
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_retained_earnings_rollforward(cur)
        assert checker.results == []

    def test_null_dividends_paid_treated_as_zero(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "NODIVCO",
                        "fiscal_year": 2025,
                        "prior_retained_earnings": 1_000_000_000.0,
                        "curr_retained_earnings": 1_500_000_000.0,
                        "net_income": 500_000_000.0,  # exact tie-out with no dividends
                        "dividends_paid": None,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_retained_earnings_rollforward(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_retained_earnings_rollforward(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (symbol)" in executed_sql
        assert "ORDER BY symbol, fiscal_year DESC" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_retained_earnings_rollforward(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "retained_earnings_rollforward"
        assert checker.results[0].severity == ERROR


class TestCashflowActivitiesSumToNetChange:
    def test_flags_row_beyond_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "BADCF",
                        "fiscal_year": 2025,
                        "operating_cash_flow": 100_000_000.0,
                        "investing_cash_flow": -20_000_000.0,
                        "financing_cash_flow": -10_000_000.0,
                        # implied 70M vs tagged 40M - way beyond 10%/$1M tolerance
                        "net_change_cash": 40_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_cashflow_activities_sum_to_net_change(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "cashflow_activities_sum_to_net_change"

    def test_does_not_flag_within_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "GOODCF",
                        "fiscal_year": 2025,
                        "operating_cash_flow": 100_000_000.0,
                        "investing_cash_flow": -20_000_000.0,
                        "financing_cash_flow": -10_000_000.0,
                        "net_change_cash": 70_000_000.0,  # exact: 100 - 20 - 10 = 70
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_cashflow_activities_sum_to_net_change(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_cashflow_activities_sum_to_net_change(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (symbol)" in executed_sql
        assert "ORDER BY symbol, fiscal_year DESC" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_cashflow_activities_sum_to_net_change(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "cashflow_activities_sum_to_net_change"
        assert checker.results[0].severity == ERROR


class TestQuickRatioLeCurrentRatio:
    """Covers check_quick_ratio_le_current_ratio, which had no dedicated test class despite
    being wired into run() - a pre-existing coverage gap in this file (the check itself landed
    in `56d7a2fd5`, this worktree's test file was never updated to match). Added 2026-09-07
    alongside the current_assets/current_liabilities checks below."""

    def test_flags_quick_ratio_above_current_ratio(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "BADQR",
                        "current_ratio": 1.5,
                        "quick_ratio": 2.0,  # structurally impossible - quick excludes inventory
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quick_ratio_le_current_ratio(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quick_ratio_le_current_ratio"
        assert checker.results[0].details["examples"][0]["symbol"] == "BADQR"

    def test_does_not_flag_quick_ratio_within_current_ratio(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "GOODQR",
                        "current_ratio": 1.5,
                        "quick_ratio": 1.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quick_ratio_le_current_ratio(cur)
        assert checker.results == []

    def test_does_not_flag_equal_ratios(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "NOINVCO",
                        "current_ratio": 1.5,
                        "quick_ratio": 1.5,  # no inventory - quick == current is legitimate
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quick_ratio_le_current_ratio(cur)
        assert checker.results == []

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_quick_ratio_le_current_ratio(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quick_ratio_le_current_ratio"
        assert checker.results[0].severity == ERROR


class TestCurrentAssetsLeTotalAssets:
    def test_flags_current_assets_above_total_assets(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "BADCA",
                        "fiscal_year": 2025,
                        "total_assets": 20_000_000_000.0,
                        "current_assets": 130_000_000_000.0,  # far exceeds total_assets
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_current_assets_le_total_assets(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "current_assets_le_total_assets"
        assert checker.results[0].details["examples"][0]["symbol"] == "BADCA"

    def test_does_not_flag_current_assets_within_total_assets(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "GOODCA",
                        "fiscal_year": 2025,
                        "total_assets": 1_000_000_000.0,
                        "current_assets": 400_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_current_assets_le_total_assets(cur)
        assert checker.results == []

    def test_does_not_flag_current_assets_equal_total_assets(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "ALLCURR",
                        "fiscal_year": 2025,
                        "total_assets": 1_000_000_000.0,
                        "current_assets": 1_000_000_000.0,  # no non-current assets - legitimate
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_current_assets_le_total_assets(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_current_assets_le_total_assets(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (b.symbol)" in executed_sql
        assert "ORDER BY b.symbol, b.fiscal_year DESC" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_current_assets_le_total_assets(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "current_assets_le_total_assets"
        assert checker.results[0].severity == ERROR


class TestCurrentLiabilitiesLeTotalLiabilities:
    def test_flags_current_liabilities_above_total_liabilities(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "BADCL",
                        "fiscal_year": 2025,
                        "total_liabilities": 11_000_000_000.0,
                        "current_liabilities": 69_000_000_000.0,  # far exceeds total_liabilities
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_current_liabilities_le_total_liabilities(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "current_liabilities_le_total_liabilities"
        assert checker.results[0].details["examples"][0]["symbol"] == "BADCL"

    def test_does_not_flag_current_liabilities_within_total_liabilities(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "GOODCL",
                        "fiscal_year": 2025,
                        "total_liabilities": 1_000_000_000.0,
                        "current_liabilities": 300_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_current_liabilities_le_total_liabilities(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_current_liabilities_le_total_liabilities(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (b.symbol)" in executed_sql
        assert "ORDER BY b.symbol, b.fiscal_year DESC" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_current_liabilities_le_total_liabilities(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "current_liabilities_le_total_liabilities"
        assert checker.results[0].severity == ERROR


class TestLongTermDebtLeTotalLiabilities:
    def test_flags_long_term_debt_above_total_liabilities(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "BADLTD",
                        "fiscal_year": 2018,
                        "total_liabilities": 719_795_000.0,
                        "long_term_debt": 19_094_000_000.0,  # far exceeds total_liabilities
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_long_term_debt_le_total_liabilities(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "long_term_debt_le_total_liabilities"
        assert checker.results[0].details["examples"][0]["symbol"] == "BADLTD"

    def test_does_not_flag_long_term_debt_within_total_liabilities(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "GOODLTD",
                        "fiscal_year": 2025,
                        "total_liabilities": 1_000_000_000.0,
                        "long_term_debt": 400_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_long_term_debt_le_total_liabilities(cur)
        assert checker.results == []

    def test_does_not_flag_long_term_debt_equal_total_liabilities(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "ALLDEBT",
                        "fiscal_year": 2025,
                        "total_liabilities": 1_000_000_000.0,
                        "long_term_debt": 1_000_000_000.0,  # no other liabilities - legitimate
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_long_term_debt_le_total_liabilities(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_long_term_debt_le_total_liabilities(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (b.symbol)" in executed_sql
        assert "ORDER BY b.symbol, b.fiscal_year DESC" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_long_term_debt_le_total_liabilities(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "long_term_debt_le_total_liabilities"
        assert checker.results[0].severity == ERROR


class TestOperatingIncomeUpperBound:
    def test_flags_operating_income_exceeding_bound(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "BADOI",
                        "fiscal_year": 2025,
                        "gross_profit": 1_000_000_000.0,
                        "operating_expenses": 400_000_000.0,
                        # ceiling is 600M; 900M is far beyond even the 10%/floor tolerance
                        "operating_income": 900_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_operating_income_upper_bound(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "operating_income_upper_bound"
        assert checker.results[0].details["examples"][0]["symbol"] == "BADOI"

    def test_does_not_flag_operating_income_below_bound(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "GOODOI",
                        "fiscal_year": 2025,
                        "gross_profit": 1_000_000_000.0,
                        "operating_expenses": 400_000_000.0,
                        # ceiling is 600M; 350M is well below - other opex lines (R&D etc) explain it
                        "operating_income": 350_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_operating_income_upper_bound(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_operating_income_upper_bound(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (i.symbol)" in executed_sql
        assert "ORDER BY i.symbol, i.fiscal_year DESC" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_operating_income_upper_bound(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "operating_income_upper_bound"
        assert checker.results[0].severity == ERROR


class TestGoodwillLeTotalAssets:
    def test_flags_goodwill_above_total_assets(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "BADGW",
                        "fiscal_year": 2024,
                        "total_assets": 50_578_000.0,
                        "goodwill": 1_005_778_000.0,  # far exceeds total_assets
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_goodwill_le_total_assets(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "goodwill_le_total_assets"
        assert checker.results[0].details["examples"][0]["symbol"] == "BADGW"

    def test_does_not_flag_goodwill_within_total_assets(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "GOODGW",
                        "fiscal_year": 2025,
                        "total_assets": 1_000_000_000.0,
                        "goodwill": 200_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_goodwill_le_total_assets(cur)
        assert checker.results == []

    def test_does_not_flag_goodwill_equal_total_assets(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "ALLGW",
                        "fiscal_year": 2025,
                        "total_assets": 1_000_000_000.0,
                        "goodwill": 1_000_000_000.0,  # no other assets - legitimate
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_goodwill_le_total_assets(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_goodwill_le_total_assets(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (b.symbol)" in executed_sql
        assert "ORDER BY b.symbol, b.fiscal_year DESC" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_goodwill_le_total_assets(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "goodwill_le_total_assets"
        assert checker.results[0].severity == ERROR


class TestAccountsPayableLeCurrentLiabilities:
    def test_flags_accounts_payable_above_current_liabilities(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "BADAP",
                        "fiscal_year": 2021,
                        "current_liabilities": 367_953.0,
                        "accounts_payable": 12_680_000.0,  # far exceeds current_liabilities
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_accounts_payable_le_current_liabilities(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "accounts_payable_le_current_liabilities"
        assert checker.results[0].details["examples"][0]["symbol"] == "BADAP"

    def test_does_not_flag_accounts_payable_within_current_liabilities(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "GOODAP",
                        "fiscal_year": 2025,
                        "current_liabilities": 1_000_000_000.0,
                        "accounts_payable": 200_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_accounts_payable_le_current_liabilities(cur)
        assert checker.results == []

    def test_does_not_flag_accounts_payable_equal_current_liabilities(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "ALLAP",
                        "fiscal_year": 2025,
                        "current_liabilities": 1_000_000_000.0,
                        "accounts_payable": 1_000_000_000.0,  # no other current liabilities
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_accounts_payable_le_current_liabilities(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_accounts_payable_le_current_liabilities(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (b.symbol)" in executed_sql
        assert "ORDER BY b.symbol, b.fiscal_year DESC" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_accounts_payable_le_current_liabilities(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "accounts_payable_le_current_liabilities"
        assert checker.results[0].severity == ERROR


class TestCashLeCurrentAssets:
    def test_flags_cash_above_current_assets(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "BADCASH",
                        "fiscal_year": 2021,
                        "current_assets": 901_355.0,
                        "cash_and_equivalents": 775_600_000.0,  # far exceeds current_assets
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_cash_le_current_assets(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "cash_le_current_assets"
        assert checker.results[0].details["examples"][0]["symbol"] == "BADCASH"

    def test_does_not_flag_cash_within_current_assets(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "GOODCASH",
                        "fiscal_year": 2025,
                        "current_assets": 1_000_000_000.0,
                        "cash_and_equivalents": 200_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_cash_le_current_assets(cur)
        assert checker.results == []

    def test_does_not_flag_cash_equal_current_assets(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "ALLCASH",
                        "fiscal_year": 2025,
                        "current_assets": 1_000_000_000.0,
                        "cash_and_equivalents": 1_000_000_000.0,  # no other current assets
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_cash_le_current_assets(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_cash_le_current_assets(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (b.symbol)" in executed_sql
        assert "ORDER BY b.symbol, b.fiscal_year DESC" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_cash_le_current_assets(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "cash_le_current_assets"
        assert checker.results[0].severity == ERROR


class TestInventoryLeCurrentAssets:
    def test_flags_inventory_above_current_assets(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "BADINV",
                        "fiscal_year": 2022,
                        "current_assets": 1_021_603.0,
                        "inventory": 1_492_000_000.0,  # far exceeds current_assets
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_inventory_le_current_assets(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "inventory_le_current_assets"
        assert checker.results[0].details["examples"][0]["symbol"] == "BADINV"

    def test_does_not_flag_inventory_within_current_assets(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "GOODINV",
                        "fiscal_year": 2025,
                        "current_assets": 1_000_000_000.0,
                        "inventory": 200_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_inventory_le_current_assets(cur)
        assert checker.results == []

    def test_does_not_flag_inventory_equal_current_assets(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "ALLINV",
                        "fiscal_year": 2025,
                        "current_assets": 1_000_000_000.0,
                        "inventory": 1_000_000_000.0,  # no other current assets
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_inventory_le_current_assets(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_inventory_le_current_assets(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (b.symbol)" in executed_sql
        assert "ORDER BY b.symbol, b.fiscal_year DESC" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_inventory_le_current_assets(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "inventory_le_current_assets"
        assert checker.results[0].severity == ERROR


class TestRunAggregatesAllChecks:
    def test_run_calls_all_nineteen_checks(self) -> None:
        cur = _mock_cursor([[]] * 19)
        checker = _checker()
        results = checker.run(cur)
        assert results == []
        assert cur.execute.call_count == 19
