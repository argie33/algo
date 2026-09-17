"""Regression tests for three 2026-09-17 fixes (goal session: xbrl_yfinance_line_item_report
remediation follow-up, verifying a prior agent's ZERO_FIRST_WRITE_GUARD_FIELDS work and finding
these three additional bugs):

1. RAVE (Rave Restaurant Group) FY2022: real, nonzero "CostOfRevenue" ($1,000) and real
   "FranchisorCosts" ($3,284,000) are genuinely ADDITIVE for this fiscal year - live-confirmed
   sum $3,285,000 is an EXACT match to yfinance. franchisor_costs is fallback-only, so the
   ordinary fallback-only gate blocked the sum from ever happening even though
   ADDITIVE_CONCEPT_PAIRS already knew about the pair.

2. PED (PEDEVCO Corp) FY2023/FY2024: real, nonzero but immaterial "ReceivablesNetCurrent"
   ($42,000 FY2023, $293,000 FY2024) blocks the real, much larger "AccountsReceivableNet"
   ($5,790,000 FY2023, $7,995,000 FY2024 - EXACT yfinance matches). Neither value is exactly
   $0, so the existing exact-zero ZERO_FIRST_WRITE_GUARD_FIELDS mechanism doesn't apply -
   needs is_accounts_receivable_net_overriding_narrow_receivables_net_current.

3. DTST (Data Storage Corp) FY2021: real, nonzero "DividendsPreferredStock" ($63,683) blocks
   the real, much larger "DividendsShareBasedCompensationCash" ($1,179,357 - the yfinance
   match). Needs is_share_based_comp_dividends_overriding_narrow_preferred_stock_dividends.

4. INR (Infinity Natural Resources) FY2022/FY2024: the plain "StockholdersEquity" concept's
   own real $0 (LLC-structured pre-IPO) blocks the real, nonzero "MembersEquity" fallback
   concept ($149,506,000 FY2022, $508,242,000 FY2024 - EXACT yfinance matches). Both values
   ARE exactly $0/nonzero, so this one just needed "stockholders_equity" added to
   ZERO_FIRST_WRITE_GUARD_FIELDS (no new guard function).

See loaders/helpers/sec_zero_component_guards.py's docstrings on ADDITIVE_CONCEPT_PAIRS,
is_accounts_receivable_net_overriding_narrow_receivables_net_current,
is_share_based_comp_dividends_overriding_narrow_preferred_stock_dividends, and
ZERO_FIRST_WRITE_GUARD_FIELDS for the guards this tests.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


def _income_loader() -> SecEdgarStatementLoader:
    loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
    loader.table_name = "annual_income_statement"
    loader.period = "annual"
    loader.statement_type = "income"
    loader._schema_cols = frozenset({"symbol", "fiscal_year", "cost_of_revenue", "data_unavailable", "reason"})
    loader._field_mapping = {
        "cost_of_revenue": "cost_of_revenue",
        "franchisor_costs": "cost_of_revenue",
        "data_unavailable": "data_unavailable",
        "reason": "reason",
    }
    loader._fallback_only_fields = frozenset({"franchisor_costs"})
    loader._reit_only_fallback_fields = frozenset()
    loader._reit_symbols = frozenset()
    loader._insurance_symbols = frozenset()
    return loader


def _balance_loader() -> SecEdgarStatementLoader:
    loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
    loader.table_name = "annual_balance_sheet"
    loader.period = "annual"
    loader.statement_type = "balance"
    loader._schema_cols = frozenset(
        {
            "symbol",
            "fiscal_year",
            "accounts_receivable",
            "stockholders_equity",
            "data_unavailable",
            "reason",
        }
    )
    loader._field_mapping = {
        "receivables_net_current": "accounts_receivable",
        "accounts_receivable_net": "accounts_receivable",
        "stockholders_equity": "stockholders_equity",
        "members_equity": "stockholders_equity",
        "data_unavailable": "data_unavailable",
        "reason": "reason",
    }
    loader._fallback_only_fields = frozenset({"receivables_net_current", "accounts_receivable_net", "members_equity"})
    loader._reit_only_fallback_fields = frozenset()
    loader._reit_symbols = frozenset()
    loader._insurance_symbols = frozenset()
    return loader


def _cashflow_loader() -> SecEdgarStatementLoader:
    loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
    loader.table_name = "annual_cash_flow"
    loader.period = "annual"
    loader.statement_type = "cashflow"
    loader._schema_cols = frozenset(
        {"symbol", "fiscal_year", "dividends_paid", "operating_cash_flow", "capex", "data_unavailable", "reason"}
    )
    loader._field_mapping = {
        "dividends": "dividends_paid",
        "dividends_preferred_stock": "dividends_paid",
        "dividends_share_based_compensation_cash": "dividends_paid",
        "data_unavailable": "data_unavailable",
        "reason": "reason",
    }
    loader._fallback_only_fields = frozenset({"dividends_preferred_stock", "dividends_share_based_compensation_cash"})
    loader._reit_only_fallback_fields = frozenset()
    loader._reit_symbols = frozenset()
    loader._insurance_symbols = frozenset()
    return loader


class TestRaveCostOfRevenueAdditive:
    def test_rave_fy2022_cost_of_revenue_and_franchisor_costs_sum(self) -> None:
        loader = _income_loader()
        row = {
            "symbol": "RAVE",
            "fiscal_year": 2022,
            "cost_of_revenue": 1_000.0,
            "franchisor_costs": 3_284_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["cost_of_revenue"] == 3_285_000.0

    def test_franchisor_costs_alone_still_works_when_cost_of_revenue_absent(self) -> None:
        """FY2023-style shape: no plain CostOfRevenue fact at all - franchisor_costs should
        still populate cost_of_revenue on its own."""
        loader = _income_loader()
        row = {"symbol": "RAVE", "fiscal_year": 2023, "franchisor_costs": 3_956_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["cost_of_revenue"] == 3_956_000.0


class TestPedAccountsReceivableOverride:
    def test_ped_fy2023_accounts_receivable_net_overrides_narrow_receivables_net_current(
        self,
    ) -> None:
        loader = _balance_loader()
        row = {
            "symbol": "PED",
            "fiscal_year": 2023,
            "receivables_net_current": 42_000.0,
            "accounts_receivable_net": 5_790_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["accounts_receivable"] == 5_790_000.0

    def test_modest_gap_does_not_override(self) -> None:
        loader = _balance_loader()
        row = {
            "symbol": "TESTCO",
            "fiscal_year": 2025,
            "receivables_net_current": 1_000_000.0,
            "accounts_receivable_net": 1_200_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["accounts_receivable"] == 1_000_000.0


class TestDtstDividendsShareBasedCompOverride:
    def test_dtst_fy2021_share_based_comp_overrides_narrow_preferred_stock_dividends(self) -> None:
        loader = _cashflow_loader()
        row = {
            "symbol": "DTST",
            "fiscal_year": 2021,
            "dividends_preferred_stock": 63_683.0,
            "dividends_share_based_compensation_cash": 1_179_357.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["dividends_paid"] == 1_179_357.0

    def test_modest_gap_does_not_override(self) -> None:
        loader = _cashflow_loader()
        row = {
            "symbol": "TESTCO",
            "fiscal_year": 2025,
            "dividends_preferred_stock": 1_000_000.0,
            "dividends_share_based_compensation_cash": 1_200_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["dividends_paid"] == 1_000_000.0


class TestInrStockholdersEquityZeroFirstWrite:
    def test_inr_fy2022_real_zero_stockholders_equity_does_not_block_members_equity(self) -> None:
        loader = _balance_loader()
        row = {
            "symbol": "INR",
            "fiscal_year": 2022,
            "stockholders_equity": 0.0,
            "members_equity": 149_506_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["stockholders_equity"] == 149_506_000.0

    def test_inr_fy2025_real_stockholders_equity_still_protected_from_zero_overwrite(self) -> None:
        """Mirror-image FY2025 shape (already-fixed via ZERO_OVERWRITE_GUARD_FIELDS) must
        remain unaffected."""
        loader = _balance_loader()
        row = {
            "symbol": "INR",
            "fiscal_year": 2025,
            "stockholders_equity": 307_139_000.0,
            "members_equity": 0.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["stockholders_equity"] == 307_139_000.0
