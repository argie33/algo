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


class TestQuarterlyBalanceSheetIdentity:
    """ADDED 2026-09-07: quarterly mirror of TestBalanceSheetIdentity, added once the
    noncontrolling_interest (migration 1265) and retained_earnings (migration 1266) schema
    gaps on quarterly_balance_sheet closed."""

    def test_flags_row_beyond_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "BADCO",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "total_assets": 1000.0,
                        "total_liabilities": 400.0,
                        "stockholders_equity": 400.0,  # off by 200, 20% of assets
                        "noncontrolling_interest": None,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_balance_sheet_identity(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_balance_sheet_identity"
        assert checker.results[0].details["count"] == 1
        assert checker.results[0].details["examples"][0]["symbol"] == "BADCO"
        assert checker.results[0].details["examples"][0]["fiscal_quarter"] == 2

    def test_does_not_flag_within_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "GOODCO",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 3,
                        "total_assets": 1000.0,
                        "total_liabilities": 600.0,
                        "stockholders_equity": 400.0,  # exact tie-out
                        "noncontrolling_interest": None,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_balance_sheet_identity(cur)
        assert checker.results == []

    def test_noncontrolling_interest_closes_identity(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "XOM",
                        "fiscal_year": 2009,
                        "fiscal_quarter": 4,
                        "total_assets": 233_323_000_000.0,
                        "total_liabilities": 117_931_000_000.0,
                        "stockholders_equity": 110_569_000_000.0,
                        "noncontrolling_interest": 4_823_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_balance_sheet_identity(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_period_per_symbol(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_quarterly_balance_sheet_identity(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (b.symbol)" in executed_sql
        assert "ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_quarterly_balance_sheet_identity(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_balance_sheet_identity"
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

    def test_query_prefers_combined_restricted_cash_when_present(self) -> None:
        """FIXED 2026-09-07 (ADP live-confirmed, migration 1267): a filer with material
        restricted cash reconciles OCF+ICF+FCF to cash_and_restricted_cash_combined, not
        unrestricted cash_and_equivalents alone - see check_cashflow_reconciliation's own
        docstring for the full evidence."""
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_cashflow_reconciliation(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "COALESCE(cash_and_restricted_cash_combined, cash_and_equivalents)" in executed_sql

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
                        "common_stock_repurchased": None,
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
                        "common_stock_repurchased": None,
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
                        "common_stock_repurchased": None,
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

    def test_constructive_retirement_buyback_explains_gap_not_flagged(self) -> None:
        """FIXED 2026-09-07: AAPL-style filer that charges buybacks against retained earnings
        (constructive retirement method) - real numbers, AAPL FY2025 (see this check's own
        docstring for the full evidence)."""
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "AAPL",
                        "fiscal_year": 2025,
                        "prior_retained_earnings": -19_154_000_000.0,
                        "curr_retained_earnings": -14_264_000_000.0,
                        "net_income": 112_010_000_000.0,
                        "dividends_paid": 15_421_000_000.0,
                        "common_stock_repurchased": 90_711_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_retained_earnings_rollforward(cur)
        assert checker.results == []

    def test_buyback_present_but_gap_still_unexplained_still_flagged(self) -> None:
        """A buyback figure that DOESN'T close the gap must still flag - OR-logic, not a blind
        override."""
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "STILLBAD",
                        "fiscal_year": 2025,
                        "prior_retained_earnings": 1_000_000_000.0,
                        "curr_retained_earnings": 1_100_000_000.0,
                        "net_income": 500_000_000.0,  # implied 1.5B vs tagged 1.1B
                        "dividends_paid": None,
                        "common_stock_repurchased": 10_000_000.0,  # far too small to explain 400M gap
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_retained_earnings_rollforward(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "retained_earnings_rollforward"

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


class TestQuarterlyGrossProfitIdentity:
    def test_flags_row_beyond_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QBAD",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "revenue": 100_000_000.0,
                        "cost_of_revenue": 90_000_000.0,
                        "gross_profit": 50_000_000.0,  # implied 10M, off by 40M (40% of revenue)
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_gross_profit_identity(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_gross_profit_identity"
        assert checker.results[0].details["examples"][0]["symbol"] == "QBAD"

    def test_does_not_flag_within_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QGOOD",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "revenue": 1000.0,
                        "cost_of_revenue": 600.0,
                        "gross_profit": 400.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_gross_profit_identity(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year_and_quarter(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_quarterly_gross_profit_identity(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (i.symbol)" in executed_sql
        assert "ORDER BY i.symbol, i.fiscal_year DESC, i.fiscal_quarter DESC" in executed_sql
        assert "quarterly_income_statement" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_quarterly_gross_profit_identity(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_gross_profit_identity"
        assert checker.results[0].severity == ERROR


class TestFreeCashFlowIdentity:
    def test_flags_row_beyond_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "FCFBAD",
                        "fiscal_year": 2025,
                        "operating_cash_flow": 1_000_000.0,
                        "capex": 200_000.0,
                        "free_cash_flow": 100_000.0,  # implied 800,000, way off
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_free_cash_flow_identity(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "free_cash_flow_identity"
        assert checker.results[0].details["examples"][0]["symbol"] == "FCFBAD"

    def test_does_not_flag_within_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "FCFGOOD",
                        "fiscal_year": 2025,
                        "operating_cash_flow": 1_000_000.0,
                        "capex": 200_000.0,
                        "free_cash_flow": 800_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_free_cash_flow_identity(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_free_cash_flow_identity(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (symbol)" in executed_sql
        assert "ORDER BY symbol, fiscal_year DESC" in executed_sql
        assert "annual_cash_flow" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_free_cash_flow_identity(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "free_cash_flow_identity"
        assert checker.results[0].severity == ERROR


class TestQuarterlyFreeCashFlowIdentity:
    def test_flags_row_beyond_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QFCFBAD",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "operating_cash_flow": 1_000_000.0,
                        "capex": 200_000.0,
                        "free_cash_flow": 100_000.0,  # implied 800,000, way off
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_free_cash_flow_identity(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_free_cash_flow_identity"
        assert checker.results[0].details["examples"][0]["symbol"] == "QFCFBAD"

    def test_does_not_flag_within_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QFCFGOOD",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "operating_cash_flow": 1_000_000.0,
                        "capex": 200_000.0,
                        "free_cash_flow": 800_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_free_cash_flow_identity(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year_and_quarter(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_quarterly_free_cash_flow_identity(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (symbol)" in executed_sql
        assert "ORDER BY symbol, fiscal_year DESC, fiscal_quarter DESC" in executed_sql
        assert "quarterly_cash_flow" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_quarterly_free_cash_flow_identity(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_free_cash_flow_identity"
        assert checker.results[0].severity == ERROR


class TestQuarterlyDilutedGeBasicShares:
    def test_flags_diluted_below_basic(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QSHAREBAD",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "shares_outstanding_basic": 1_000_000.0,
                        "shares_outstanding_diluted": 900_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_diluted_ge_basic_shares(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_diluted_ge_basic_shares"
        assert checker.results[0].details["examples"][0]["symbol"] == "QSHAREBAD"

    def test_does_not_flag_diluted_above_basic(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QSHAREGOOD",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "shares_outstanding_basic": 1_000_000.0,
                        "shares_outstanding_diluted": 1_050_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_diluted_ge_basic_shares(cur)
        assert checker.results == []

    def test_does_not_flag_equal_counts(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QSHAREEQ",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "shares_outstanding_basic": 1_000_000.0,
                        "shares_outstanding_diluted": 1_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_diluted_ge_basic_shares(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year_and_quarter(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_quarterly_diluted_ge_basic_shares(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (i.symbol)" in executed_sql
        assert "ORDER BY i.symbol, i.fiscal_year DESC, i.fiscal_quarter DESC" in executed_sql
        assert "quarterly_income_statement" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_quarterly_diluted_ge_basic_shares(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_diluted_ge_basic_shares"
        assert checker.results[0].severity == ERROR


class TestQuarterlyInventoryLeCurrentAssets:
    def test_flags_inventory_above_current_assets(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QINVBAD",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "current_assets": 1_000_000.0,
                        "inventory": 5_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_inventory_le_current_assets(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_inventory_le_current_assets"
        assert checker.results[0].details["examples"][0]["symbol"] == "QINVBAD"

    def test_does_not_flag_inventory_within_current_assets(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QINVGOOD",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "current_assets": 1_000_000.0,
                        "inventory": 200_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_inventory_le_current_assets(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year_and_quarter(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_quarterly_inventory_le_current_assets(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (b.symbol)" in executed_sql
        assert "ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC" in executed_sql
        assert "quarterly_balance_sheet" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_quarterly_inventory_le_current_assets(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_inventory_le_current_assets"
        assert checker.results[0].severity == ERROR


class TestQuarterlyAccountsReceivableLeCurrentAssets:
    def test_flags_ar_above_current_assets(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QARBAD",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "current_assets": 1_000_000.0,
                        "accounts_receivable": 5_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_accounts_receivable_le_current_assets(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_accounts_receivable_le_current_assets"
        assert checker.results[0].details["examples"][0]["symbol"] == "QARBAD"

    def test_does_not_flag_ar_within_current_assets(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QARGOOD",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "current_assets": 1_000_000.0,
                        "accounts_receivable": 200_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_accounts_receivable_le_current_assets(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year_and_quarter(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_quarterly_accounts_receivable_le_current_assets(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (b.symbol)" in executed_sql
        assert "ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC" in executed_sql
        assert "quarterly_balance_sheet" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_quarterly_accounts_receivable_le_current_assets(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_accounts_receivable_le_current_assets"
        assert checker.results[0].severity == ERROR


class TestQuarterlyPpeNetLeTotalAssets:
    def test_flags_ppe_net_above_total_assets(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QPPEBAD",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "total_assets": 1_000_000.0,
                        "ppe_net": 5_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_ppe_net_le_total_assets(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_ppe_net_le_total_assets"
        assert checker.results[0].details["examples"][0]["symbol"] == "QPPEBAD"

    def test_does_not_flag_ppe_net_within_total_assets(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QPPEGOOD",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "total_assets": 1_000_000.0,
                        "ppe_net": 200_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_ppe_net_le_total_assets(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year_and_quarter(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_quarterly_ppe_net_le_total_assets(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (b.symbol)" in executed_sql
        assert "ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC" in executed_sql
        assert "quarterly_balance_sheet" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_quarterly_ppe_net_le_total_assets(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_ppe_net_le_total_assets"
        assert checker.results[0].severity == ERROR


class TestQuarterlyShortTermDebtLeCurrentLiabilities:
    def test_flags_short_term_debt_above_current_liabilities(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QSTDBAD",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "current_liabilities": 1_000_000.0,
                        "short_term_debt": 5_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_short_term_debt_le_current_liabilities(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_short_term_debt_le_current_liabilities"
        assert checker.results[0].details["examples"][0]["symbol"] == "QSTDBAD"

    def test_does_not_flag_short_term_debt_within_current_liabilities(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QSTDGOOD",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "current_liabilities": 1_000_000.0,
                        "short_term_debt": 200_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_short_term_debt_le_current_liabilities(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year_and_quarter(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_quarterly_short_term_debt_le_current_liabilities(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (b.symbol)" in executed_sql
        assert "ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC" in executed_sql
        assert "quarterly_balance_sheet" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_quarterly_short_term_debt_le_current_liabilities(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_short_term_debt_le_current_liabilities"
        assert checker.results[0].severity == ERROR


class TestQuarterlyOperatingLeaseLiabilityLeTotalLiabilities:
    def test_flags_operating_lease_liability_above_total_liabilities(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QOLLBAD",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "total_liabilities": 1_000_000.0,
                        "operating_lease_liability": 5_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_operating_lease_liability_le_total_liabilities(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_operating_lease_liability_le_total_liabilities"
        assert checker.results[0].details["examples"][0]["symbol"] == "QOLLBAD"

    def test_does_not_flag_operating_lease_liability_within_total_liabilities(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QOLLGOOD",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "total_liabilities": 1_000_000.0,
                        "operating_lease_liability": 200_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_operating_lease_liability_le_total_liabilities(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year_and_quarter(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_quarterly_operating_lease_liability_le_total_liabilities(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (b.symbol)" in executed_sql
        assert "ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC" in executed_sql
        assert "quarterly_balance_sheet" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_quarterly_operating_lease_liability_le_total_liabilities(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_operating_lease_liability_le_total_liabilities"
        assert checker.results[0].severity == ERROR


class TestQuarterlyFinanceLeaseLiabilityLeTotalLiabilities:
    def test_flags_finance_lease_liability_above_total_liabilities(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QFLLBAD",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "total_liabilities": 1_000_000.0,
                        "finance_lease_liability": 5_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_finance_lease_liability_le_total_liabilities(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_finance_lease_liability_le_total_liabilities"
        assert checker.results[0].details["examples"][0]["symbol"] == "QFLLBAD"

    def test_does_not_flag_finance_lease_liability_within_total_liabilities(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QFLLGOOD",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "total_liabilities": 1_000_000.0,
                        "finance_lease_liability": 200_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_finance_lease_liability_le_total_liabilities(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year_and_quarter(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_quarterly_finance_lease_liability_le_total_liabilities(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (b.symbol)" in executed_sql
        assert "ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC" in executed_sql
        assert "quarterly_balance_sheet" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_quarterly_finance_lease_liability_le_total_liabilities(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_finance_lease_liability_le_total_liabilities"
        assert checker.results[0].severity == ERROR


class TestQuarterlyDilutedEpsLeBasicEps:
    def test_flags_diluted_eps_above_basic_eps(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QEPSBAD",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "diluted_eps": 5.00,
                        "earnings_per_share": 1.00,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_diluted_eps_le_basic_eps(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_diluted_eps_le_basic_eps"
        assert checker.results[0].details["examples"][0]["symbol"] == "QEPSBAD"

    def test_flags_less_negative_diluted_loss_per_share(self) -> None:
        """Antidilution violation in the loss-period direction: a less-negative diluted
        loss-per-share than basic is just as much a violation as an inflated profit figure."""
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QEPSLOSS",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "diluted_eps": -0.16,
                        "earnings_per_share": -377.10,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_diluted_eps_le_basic_eps(cur)
        assert len(checker.results) == 1
        assert checker.results[0].details["examples"][0]["symbol"] == "QEPSLOSS"

    def test_does_not_flag_diluted_eps_within_basic_eps(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QEPSGOOD",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "diluted_eps": 0.90,
                        "earnings_per_share": 1.00,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_diluted_eps_le_basic_eps(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year_and_quarter(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_quarterly_diluted_eps_le_basic_eps(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (i.symbol)" in executed_sql
        assert "ORDER BY i.symbol, i.fiscal_year DESC, i.fiscal_quarter DESC" in executed_sql
        assert "quarterly_income_statement" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_quarterly_diluted_eps_le_basic_eps(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_diluted_eps_le_basic_eps"
        assert checker.results[0].severity == ERROR


class TestAccountsReceivableLeCurrentAssets:
    def test_flags_row_beyond_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "BAD_CHECK_ACCO",
                        "fiscal_year": 2025,
                        "current_assets": 1_000_000.0,
                        "accounts_receivable": 2_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_accounts_receivable_le_current_assets(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "accounts_receivable_le_current_assets"
        assert checker.results[0].details["examples"][0]["symbol"] == "BAD_CHECK_ACCO"

    def test_does_not_flag_within_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "GOOD_CHECK_ACCO",
                        "fiscal_year": 2025,
                        "current_assets": 1_000_000.0,
                        "accounts_receivable": 200_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_accounts_receivable_le_current_assets(cur)
        assert checker.results == []

    def test_does_not_flag_equal_values(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "EQ_CHECK_ACCO",
                        "fiscal_year": 2025,
                        "current_assets": 1_000_000.0,
                        "accounts_receivable": 1_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_accounts_receivable_le_current_assets(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_accounts_receivable_le_current_assets(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (b.symbol)" in executed_sql
        assert "ORDER BY b.symbol, b.fiscal_year DESC" in executed_sql
        assert "annual_balance_sheet" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_accounts_receivable_le_current_assets(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "accounts_receivable_le_current_assets"
        assert checker.results[0].severity == ERROR


class TestPpeNetLeTotalAssets:
    def test_flags_row_beyond_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "BAD_CHECK_PPE_",
                        "fiscal_year": 2025,
                        "total_assets": 1_000_000.0,
                        "ppe_net": 2_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_ppe_net_le_total_assets(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "ppe_net_le_total_assets"
        assert checker.results[0].details["examples"][0]["symbol"] == "BAD_CHECK_PPE_"

    def test_does_not_flag_within_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "GOOD_CHECK_PPE_",
                        "fiscal_year": 2025,
                        "total_assets": 1_000_000.0,
                        "ppe_net": 200_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_ppe_net_le_total_assets(cur)
        assert checker.results == []

    def test_does_not_flag_equal_values(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "EQ_CHECK_PPE_",
                        "fiscal_year": 2025,
                        "total_assets": 1_000_000.0,
                        "ppe_net": 1_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_ppe_net_le_total_assets(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_ppe_net_le_total_assets(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (b.symbol)" in executed_sql
        assert "ORDER BY b.symbol, b.fiscal_year DESC" in executed_sql
        assert "annual_balance_sheet" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_ppe_net_le_total_assets(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "ppe_net_le_total_assets"
        assert checker.results[0].severity == ERROR


class TestShortTermDebtLeCurrentLiabilities:
    def test_flags_row_beyond_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "BAD_CHECK_SHOR",
                        "fiscal_year": 2025,
                        "current_liabilities": 1_000_000.0,
                        "short_term_debt": 2_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_short_term_debt_le_current_liabilities(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "short_term_debt_le_current_liabilities"
        assert checker.results[0].details["examples"][0]["symbol"] == "BAD_CHECK_SHOR"

    def test_does_not_flag_within_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "GOOD_CHECK_SHOR",
                        "fiscal_year": 2025,
                        "current_liabilities": 1_000_000.0,
                        "short_term_debt": 200_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_short_term_debt_le_current_liabilities(cur)
        assert checker.results == []

    def test_does_not_flag_equal_values(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "EQ_CHECK_SHOR",
                        "fiscal_year": 2025,
                        "current_liabilities": 1_000_000.0,
                        "short_term_debt": 1_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_short_term_debt_le_current_liabilities(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_short_term_debt_le_current_liabilities(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (b.symbol)" in executed_sql
        assert "ORDER BY b.symbol, b.fiscal_year DESC" in executed_sql
        assert "annual_balance_sheet" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_short_term_debt_le_current_liabilities(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "short_term_debt_le_current_liabilities"
        assert checker.results[0].severity == ERROR


class TestOperatingLeaseLiabilityLeTotalLiabilities:
    def test_flags_row_beyond_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "BAD_CHECK_OPER",
                        "fiscal_year": 2025,
                        "total_liabilities": 1_000_000.0,
                        "operating_lease_liability": 2_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_operating_lease_liability_le_total_liabilities(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "operating_lease_liability_le_total_liabilities"
        assert checker.results[0].details["examples"][0]["symbol"] == "BAD_CHECK_OPER"

    def test_does_not_flag_within_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "GOOD_CHECK_OPER",
                        "fiscal_year": 2025,
                        "total_liabilities": 1_000_000.0,
                        "operating_lease_liability": 200_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_operating_lease_liability_le_total_liabilities(cur)
        assert checker.results == []

    def test_does_not_flag_equal_values(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "EQ_CHECK_OPER",
                        "fiscal_year": 2025,
                        "total_liabilities": 1_000_000.0,
                        "operating_lease_liability": 1_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_operating_lease_liability_le_total_liabilities(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_operating_lease_liability_le_total_liabilities(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (b.symbol)" in executed_sql
        assert "ORDER BY b.symbol, b.fiscal_year DESC" in executed_sql
        assert "annual_balance_sheet" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_operating_lease_liability_le_total_liabilities(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "operating_lease_liability_le_total_liabilities"
        assert checker.results[0].severity == ERROR


class TestFinanceLeaseLiabilityLeTotalLiabilities:
    def test_flags_row_beyond_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "BAD_CHECK_FINA",
                        "fiscal_year": 2025,
                        "total_liabilities": 1_000_000.0,
                        "finance_lease_liability": 2_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_finance_lease_liability_le_total_liabilities(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "finance_lease_liability_le_total_liabilities"
        assert checker.results[0].details["examples"][0]["symbol"] == "BAD_CHECK_FINA"

    def test_does_not_flag_within_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "GOOD_CHECK_FINA",
                        "fiscal_year": 2025,
                        "total_liabilities": 1_000_000.0,
                        "finance_lease_liability": 200_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_finance_lease_liability_le_total_liabilities(cur)
        assert checker.results == []

    def test_does_not_flag_equal_values(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "EQ_CHECK_FINA",
                        "fiscal_year": 2025,
                        "total_liabilities": 1_000_000.0,
                        "finance_lease_liability": 1_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_finance_lease_liability_le_total_liabilities(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_finance_lease_liability_le_total_liabilities(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (b.symbol)" in executed_sql
        assert "ORDER BY b.symbol, b.fiscal_year DESC" in executed_sql
        assert "annual_balance_sheet" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_finance_lease_liability_le_total_liabilities(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "finance_lease_liability_le_total_liabilities"
        assert checker.results[0].severity == ERROR


class TestDilutedEpsLeBasicEps:
    def test_flags_diluted_more_favorable_than_basic_profit(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "BADEPS",
                        "fiscal_year": 2025,
                        "diluted_eps": 1.00,
                        "earnings_per_share": 0.50,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_diluted_eps_le_basic_eps(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "diluted_eps_le_basic_eps"
        assert checker.results[0].details["examples"][0]["symbol"] == "BADEPS"

    def test_flags_diluted_less_negative_than_basic_loss(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "BADEPSLOSS",
                        "fiscal_year": 2022,
                        "diluted_eps": -0.16,
                        "earnings_per_share": -377.10,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_diluted_eps_le_basic_eps(cur)
        assert len(checker.results) == 1
        assert checker.results[0].details["examples"][0]["symbol"] == "BADEPSLOSS"

    def test_does_not_flag_diluted_below_basic(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "GOODEPS",
                        "fiscal_year": 2025,
                        "diluted_eps": 0.95,
                        "earnings_per_share": 1.00,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_diluted_eps_le_basic_eps(cur)
        assert checker.results == []

    def test_does_not_flag_equal_eps(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "EQEPS",
                        "fiscal_year": 2025,
                        "diluted_eps": 1.00,
                        "earnings_per_share": 1.00,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_diluted_eps_le_basic_eps(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_diluted_eps_le_basic_eps(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (i.symbol)" in executed_sql
        assert "ORDER BY i.symbol, i.fiscal_year DESC" in executed_sql
        assert "annual_income_statement" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_diluted_eps_le_basic_eps(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "diluted_eps_le_basic_eps"
        assert checker.results[0].severity == ERROR


class TestQuarterlyEpsReconciliation:
    def test_flags_row_beyond_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QEPSBAD",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "net_income": 1_000_000.0,
                        "diluted_eps": 5.00,
                        "shares_outstanding_diluted": 1_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_eps_reconciliation(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_eps_reconciliation"
        assert checker.results[0].details["examples"][0]["symbol"] == "QEPSBAD"

    def test_does_not_flag_within_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QEPSGOOD",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "net_income": 1_000_000.0,
                        "diluted_eps": 1.00,
                        "shares_outstanding_diluted": 1_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_eps_reconciliation(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year_and_quarter(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_quarterly_eps_reconciliation(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (i.symbol)" in executed_sql
        assert "ORDER BY i.symbol, i.fiscal_year DESC, i.fiscal_quarter DESC" in executed_sql
        assert "quarterly_income_statement" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_quarterly_eps_reconciliation(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_eps_reconciliation"
        assert checker.results[0].severity == ERROR


class TestQuarterlyBasicEpsReconciliation:
    def test_flags_row_beyond_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QBEPSBAD",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "net_income": 1_000_000.0,
                        "earnings_per_share": 5.00,
                        "shares_outstanding_basic": 1_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_basic_eps_reconciliation(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_basic_eps_reconciliation"
        assert checker.results[0].details["examples"][0]["symbol"] == "QBEPSBAD"

    def test_does_not_flag_within_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QBEPSGOOD",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "net_income": 1_000_000.0,
                        "earnings_per_share": 1.00,
                        "shares_outstanding_basic": 1_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_basic_eps_reconciliation(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year_and_quarter(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_quarterly_basic_eps_reconciliation(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (i.symbol)" in executed_sql
        assert "ORDER BY i.symbol, i.fiscal_year DESC, i.fiscal_quarter DESC" in executed_sql
        assert "quarterly_income_statement" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_quarterly_basic_eps_reconciliation(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_basic_eps_reconciliation"
        assert checker.results[0].severity == ERROR


class TestQuarterlyPretaxToNetIncome:
    def test_flags_row_beyond_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QPTBAD",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "pretax_income": 1_000_000.0,
                        "income_tax_expense": 200_000.0,
                        "net_income": 100_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_pretax_to_net_income(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_pretax_to_net_income"
        assert checker.results[0].details["examples"][0]["symbol"] == "QPTBAD"

    def test_does_not_flag_within_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QPTGOOD",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "pretax_income": 1_000_000.0,
                        "income_tax_expense": 200_000.0,
                        "net_income": 800_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_pretax_to_net_income(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year_and_quarter(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_quarterly_pretax_to_net_income(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (i.symbol)" in executed_sql
        assert "ORDER BY i.symbol, i.fiscal_year DESC, i.fiscal_quarter DESC" in executed_sql
        assert "quarterly_income_statement" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_quarterly_pretax_to_net_income(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_pretax_to_net_income"
        assert checker.results[0].severity == ERROR


class TestQuarterlyCashflowActivitiesSumToNetChange:
    def test_flags_row_beyond_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QCFBAD",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "operating_cash_flow": 100.0,
                        "investing_cash_flow": -50.0,
                        "financing_cash_flow": -10.0,
                        "net_change_cash": 1_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_cashflow_activities_sum_to_net_change(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_cashflow_activities_sum_to_net_change"
        assert checker.results[0].details["examples"][0]["symbol"] == "QCFBAD"

    def test_does_not_flag_within_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QCFGOOD",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "operating_cash_flow": 100.0,
                        "investing_cash_flow": -50.0,
                        "financing_cash_flow": -10.0,
                        "net_change_cash": 40.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_cashflow_activities_sum_to_net_change(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year_and_quarter(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_quarterly_cashflow_activities_sum_to_net_change(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (symbol)" in executed_sql
        assert "ORDER BY symbol, fiscal_year DESC, fiscal_quarter DESC" in executed_sql
        assert "quarterly_cash_flow" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_quarterly_cashflow_activities_sum_to_net_change(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_cashflow_activities_sum_to_net_change"
        assert checker.results[0].severity == ERROR


class TestQuarterlyCurrentAssetsLeTotalAssets:
    def test_flags_row_beyond_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QBAD_CHECK_QU",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "total_assets": 1_000_000.0,
                        "current_assets": 2_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_current_assets_le_total_assets(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_current_assets_le_total_assets"
        assert checker.results[0].details["examples"][0]["symbol"] == "QBAD_CHECK_QU"

    def test_does_not_flag_within_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QGOOD_CHECK_QU",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "total_assets": 1_000_000.0,
                        "current_assets": 200_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_current_assets_le_total_assets(cur)
        assert checker.results == []

    def test_does_not_flag_equal_values(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QEQ_CHECK_QU",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "total_assets": 1_000_000.0,
                        "current_assets": 1_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_current_assets_le_total_assets(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year_and_quarter(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_quarterly_current_assets_le_total_assets(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (b.symbol)" in executed_sql
        assert "ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC" in executed_sql
        assert "quarterly_balance_sheet" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_quarterly_current_assets_le_total_assets(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_current_assets_le_total_assets"
        assert checker.results[0].severity == ERROR


class TestQuarterlyCurrentLiabilitiesLeTotalLiabilities:
    def test_flags_row_beyond_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QBAD_CHECK_QU",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "total_liabilities": 1_000_000.0,
                        "current_liabilities": 2_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_current_liabilities_le_total_liabilities(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_current_liabilities_le_total_liabilities"
        assert checker.results[0].details["examples"][0]["symbol"] == "QBAD_CHECK_QU"

    def test_does_not_flag_within_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QGOOD_CHECK_QU",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "total_liabilities": 1_000_000.0,
                        "current_liabilities": 200_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_current_liabilities_le_total_liabilities(cur)
        assert checker.results == []

    def test_does_not_flag_equal_values(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QEQ_CHECK_QU",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "total_liabilities": 1_000_000.0,
                        "current_liabilities": 1_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_current_liabilities_le_total_liabilities(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year_and_quarter(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_quarterly_current_liabilities_le_total_liabilities(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (b.symbol)" in executed_sql
        assert "ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC" in executed_sql
        assert "quarterly_balance_sheet" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_quarterly_current_liabilities_le_total_liabilities(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_current_liabilities_le_total_liabilities"
        assert checker.results[0].severity == ERROR


class TestQuarterlyLongTermDebtLeTotalLiabilities:
    def test_flags_row_beyond_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QBAD_CHECK_QU",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "total_liabilities": 1_000_000.0,
                        "long_term_debt": 2_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_long_term_debt_le_total_liabilities(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_long_term_debt_le_total_liabilities"
        assert checker.results[0].details["examples"][0]["symbol"] == "QBAD_CHECK_QU"

    def test_does_not_flag_within_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QGOOD_CHECK_QU",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "total_liabilities": 1_000_000.0,
                        "long_term_debt": 200_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_long_term_debt_le_total_liabilities(cur)
        assert checker.results == []

    def test_does_not_flag_equal_values(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QEQ_CHECK_QU",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "total_liabilities": 1_000_000.0,
                        "long_term_debt": 1_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_long_term_debt_le_total_liabilities(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year_and_quarter(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_quarterly_long_term_debt_le_total_liabilities(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (b.symbol)" in executed_sql
        assert "ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC" in executed_sql
        assert "quarterly_balance_sheet" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_quarterly_long_term_debt_le_total_liabilities(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_long_term_debt_le_total_liabilities"
        assert checker.results[0].severity == ERROR


class TestQuarterlyOperatingIncomeUpperBound:
    def test_flags_operating_income_exceeding_bound(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QOIBAD",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "gross_profit": 1_000_000_000.0,
                        "operating_expenses": 400_000_000.0,
                        # ceiling is 600M; 900M is far beyond even the 10%/floor tolerance
                        "operating_income": 900_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_operating_income_upper_bound(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_operating_income_upper_bound"
        assert checker.results[0].details["examples"][0]["symbol"] == "QOIBAD"

    def test_does_not_flag_operating_income_below_bound(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QOIGOOD",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "gross_profit": 1_000_000.0,
                        "operating_expenses": 300_000.0,
                        "operating_income": 400_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_operating_income_upper_bound(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year_and_quarter(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_quarterly_operating_income_upper_bound(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (i.symbol)" in executed_sql
        assert "ORDER BY i.symbol, i.fiscal_year DESC, i.fiscal_quarter DESC" in executed_sql
        assert "quarterly_income_statement" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_quarterly_operating_income_upper_bound(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_operating_income_upper_bound"
        assert checker.results[0].severity == ERROR


class TestQuarterlyGoodwillLeTotalAssets:
    def test_flags_row_beyond_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QBAD_CHECK_QU",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "total_assets": 1_000_000.0,
                        "goodwill": 2_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_goodwill_le_total_assets(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_goodwill_le_total_assets"
        assert checker.results[0].details["examples"][0]["symbol"] == "QBAD_CHECK_QU"

    def test_does_not_flag_within_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QGOOD_CHECK_QU",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "total_assets": 1_000_000.0,
                        "goodwill": 200_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_goodwill_le_total_assets(cur)
        assert checker.results == []

    def test_does_not_flag_equal_values(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QEQ_CHECK_QU",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "total_assets": 1_000_000.0,
                        "goodwill": 1_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_goodwill_le_total_assets(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year_and_quarter(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_quarterly_goodwill_le_total_assets(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (b.symbol)" in executed_sql
        assert "ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC" in executed_sql
        assert "quarterly_balance_sheet" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_quarterly_goodwill_le_total_assets(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_goodwill_le_total_assets"
        assert checker.results[0].severity == ERROR


class TestQuarterlyAccountsPayableLeCurrentLiabilities:
    def test_flags_row_beyond_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QBAD_CHECK_QU",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "current_liabilities": 1_000_000.0,
                        "accounts_payable": 2_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_accounts_payable_le_current_liabilities(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_accounts_payable_le_current_liabilities"
        assert checker.results[0].details["examples"][0]["symbol"] == "QBAD_CHECK_QU"

    def test_does_not_flag_within_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QGOOD_CHECK_QU",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "current_liabilities": 1_000_000.0,
                        "accounts_payable": 200_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_accounts_payable_le_current_liabilities(cur)
        assert checker.results == []

    def test_does_not_flag_equal_values(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QEQ_CHECK_QU",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "current_liabilities": 1_000_000.0,
                        "accounts_payable": 1_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_accounts_payable_le_current_liabilities(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year_and_quarter(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_quarterly_accounts_payable_le_current_liabilities(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (b.symbol)" in executed_sql
        assert "ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC" in executed_sql
        assert "quarterly_balance_sheet" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_quarterly_accounts_payable_le_current_liabilities(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_accounts_payable_le_current_liabilities"
        assert checker.results[0].severity == ERROR


class TestQuarterlyCashLeCurrentAssets:
    def test_flags_row_beyond_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QBAD_CHECK_QU",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "current_assets": 1_000_000.0,
                        "cash_and_equivalents": 2_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_cash_le_current_assets(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_cash_le_current_assets"
        assert checker.results[0].details["examples"][0]["symbol"] == "QBAD_CHECK_QU"

    def test_does_not_flag_within_tolerance(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QGOOD_CHECK_QU",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "current_assets": 1_000_000.0,
                        "cash_and_equivalents": 200_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_cash_le_current_assets(cur)
        assert checker.results == []

    def test_does_not_flag_equal_values(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QEQ_CHECK_QU",
                        "fiscal_year": 2025,
                        "fiscal_quarter": 2,
                        "current_assets": 1_000_000.0,
                        "cash_and_equivalents": 1_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_cash_le_current_assets(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year_and_quarter(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_quarterly_cash_le_current_assets(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (b.symbol)" in executed_sql
        assert "ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC" in executed_sql
        assert "quarterly_balance_sheet" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_quarterly_cash_le_current_assets(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_cash_le_current_assets"
        assert checker.results[0].severity == ERROR


class TestStockBasedCompensationNonnegative:
    def test_flags_negative_row(self) -> None:
        cur = _mock_cursor([[{"symbol": "AAMI", "fiscal_year": 2025, "stock_based_compensation": -47_700_000.0}]])
        checker = _checker()
        checker.check_stock_based_compensation_nonnegative(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "stock_based_compensation_nonnegative"
        assert checker.results[0].details["examples"][0]["symbol"] == "AAMI"

    def test_does_not_flag_nonnegative_row(self) -> None:
        cur = _mock_cursor([[{"symbol": "AAPL", "fiscal_year": 2025, "stock_based_compensation": 11_000_000_000.0}]])
        checker = _checker()
        checker.check_stock_based_compensation_nonnegative(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_stock_based_compensation_nonnegative(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "DISTINCT ON (b.symbol)" in executed_sql
        assert "ORDER BY b.symbol, b.fiscal_year DESC" in executed_sql
        assert "annual_cash_flow" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_stock_based_compensation_nonnegative(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "stock_based_compensation_nonnegative"
        assert checker.results[0].severity == ERROR


class TestQuarterlyStockBasedCompensationNonnegative:
    def test_flags_negative_row(self) -> None:
        cur = _mock_cursor(
            [[{"symbol": "AAMI", "fiscal_year": 2025, "fiscal_quarter": 4, "stock_based_compensation": -1_000.0}]]
        )
        checker = _checker()
        checker.check_quarterly_stock_based_compensation_nonnegative(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_stock_based_compensation_nonnegative"

    def test_query_dedups_to_latest_fiscal_year_and_quarter(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_quarterly_stock_based_compensation_nonnegative(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "ORDER BY b.symbol, b.fiscal_year DESC, b.fiscal_quarter DESC" in executed_sql
        assert "quarterly_cash_flow" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_quarterly_stock_based_compensation_nonnegative(cur)  # must not raise
        assert checker.results[0].severity == ERROR


class TestCommonStockRepurchasedNonnegative:
    def test_flags_negative_row(self) -> None:
        cur = _mock_cursor([[{"symbol": "JCTC", "fiscal_year": 2013, "common_stock_repurchased": -7_188.0}]])
        checker = _checker()
        checker.check_common_stock_repurchased_nonnegative(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "common_stock_repurchased_nonnegative"

    def test_does_not_flag_nonnegative_row(self) -> None:
        cur = _mock_cursor([[{"symbol": "AAPL", "fiscal_year": 2025, "common_stock_repurchased": 90_000_000_000.0}]])
        checker = _checker()
        checker.check_common_stock_repurchased_nonnegative(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_common_stock_repurchased_nonnegative(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "annual_cash_flow" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_common_stock_repurchased_nonnegative(cur)  # must not raise
        assert checker.results[0].severity == ERROR


class TestQuarterlyCommonStockRepurchasedNonnegative:
    def test_flags_negative_row(self) -> None:
        cur = _mock_cursor(
            [[{"symbol": "JCTC", "fiscal_year": 2013, "fiscal_quarter": 4, "common_stock_repurchased": -7_188.0}]]
        )
        checker = _checker()
        checker.check_quarterly_common_stock_repurchased_nonnegative(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_common_stock_repurchased_nonnegative"

    def test_query_dedups_to_latest_fiscal_year_and_quarter(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_quarterly_common_stock_repurchased_nonnegative(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "quarterly_cash_flow" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_quarterly_common_stock_repurchased_nonnegative(cur)  # must not raise
        assert checker.results[0].severity == ERROR


class TestSharesOutstandingDeiPlausibleScale:
    def test_flags_implausibly_large_row(self) -> None:
        cur = _mock_cursor(
            [[{"symbol": "EEFT", "fiscal_year": 2020, "shares_outstanding_dei": 52_752_851_000_000_000.0}]]
        )
        checker = _checker()
        checker.check_shares_outstanding_dei_plausible_scale(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "shares_outstanding_dei_plausible_scale"
        assert checker.results[0].details["examples"][0]["symbol"] == "EEFT"

    def test_flags_implausibly_small_row(self) -> None:
        cur = _mock_cursor([[{"symbol": "TINY", "fiscal_year": 2024, "shares_outstanding_dei": 52_205.0}]])
        checker = _checker()
        checker.check_shares_outstanding_dei_plausible_scale(cur)
        assert len(checker.results) == 1

    def test_does_not_flag_plausible_row(self) -> None:
        cur = _mock_cursor([[{"symbol": "PJT", "fiscal_year": 2020, "shares_outstanding_dei": 28_000_000.0}]])
        checker = _checker()
        checker.check_shares_outstanding_dei_plausible_scale(cur)
        assert checker.results == []

    def test_query_dedups_to_latest_fiscal_year(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_shares_outstanding_dei_plausible_scale(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "annual_income_statement" in executed_sql
        assert "b.shares_outstanding_dei > 0" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_shares_outstanding_dei_plausible_scale(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "shares_outstanding_dei_plausible_scale"
        assert checker.results[0].severity == ERROR


class TestQuarterlySharesOutstandingDeiPlausibleScale:
    def test_flags_implausibly_large_row(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "EEFT",
                        "fiscal_year": 2020,
                        "fiscal_quarter": 4,
                        "shares_outstanding_dei": 52_752_851_000_000_000.0,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_quarterly_shares_outstanding_dei_plausible_scale(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "quarterly_shares_outstanding_dei_plausible_scale"

    def test_query_dedups_to_latest_fiscal_year_and_quarter(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_quarterly_shares_outstanding_dei_plausible_scale(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "quarterly_income_statement" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_quarterly_shares_outstanding_dei_plausible_scale(cur)  # must not raise
        assert checker.results[0].severity == ERROR


class TestStockScoresBounds:
    def test_flags_out_of_range_score(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "ZZZZ",
                        "date": "2026-09-08",
                        "composite_score": 104.2,
                        "quality_score": 50.0,
                        "growth_score": 50.0,
                        "value_score": 50.0,
                        "risk_score": 50.0,
                        "momentum_score": -3.5,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_stock_scores_bounds(cur)
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "stock_scores_bounds"
        assert checker.results[0].details["count"] == 2
        flagged_fields = {e["field"] for e in checker.results[0].details["examples"]}
        assert flagged_fields == {"composite_score", "momentum_score"}

    def test_does_not_flag_in_range_scores(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "AAPL",
                        "date": "2026-09-08",
                        "composite_score": 59.57,
                        "quality_score": 82.83,
                        "growth_score": 68.51,
                        "value_score": 15.54,
                        "risk_score": 66.13,
                        "momentum_score": 75.98,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_stock_scores_bounds(cur)
        assert checker.results == []

    def test_does_not_flag_null_scores(self) -> None:
        cur = _mock_cursor(
            [
                [
                    {
                        "symbol": "QQQ",
                        "date": "2026-09-08",
                        "composite_score": None,
                        "quality_score": None,
                        "growth_score": None,
                        "value_score": None,
                        "risk_score": None,
                        "momentum_score": None,
                    }
                ]
            ]
        )
        checker = _checker()
        checker.check_stock_scores_bounds(cur)
        assert checker.results == []

    def test_query_uses_latest_date(self) -> None:
        cur = _mock_cursor([[]])
        checker = _checker()
        checker.check_stock_scores_bounds(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "stock_scores" in executed_sql
        assert "SELECT MAX(date) FROM stock_scores" in executed_sql

    def test_exception_is_caught_not_raised(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker.check_stock_scores_bounds(cur)  # must not raise
        assert len(checker.results) == 1
        assert checker.results[0].check_name == "stock_scores_bounds"
        assert checker.results[0].severity == ERROR


class TestRunAggregatesAllChecks:
    def test_run_calls_all_fifty_four_checks(self) -> None:
        cur = _mock_cursor([[]] * 54)
        checker = _checker()
        results = checker.run(cur)
        assert results == []
        assert cur.execute.call_count == 54
