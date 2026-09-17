"""Regression test for the 2026-09-16 fix (goal: SEC-vs-yfinance divergence sweep,
second follow-up pass): 4 more genuine dividends_paid concepts + 1 cost_of_revenue
concept found by scanning EVERY numeric fact in each filer's full companyfacts JSON for
one that exactly matches xbrl_yfinance_line_item_report's flagged value:

- DTST: "DividendsShareBasedCompensationCash" ($1,179,357)
- EVEX: "PaymentsOfDistributionsToAffiliates" ($1,372,633)
- HE (Hawaiian Electric): "PaymentsOfDividendsMinorityInterest" (a fixed $1,890,000
  every fiscal year 2008-2025)
- SEAT: "DividendsCommonStockPaidinkind" ($17,698,000)
- RAVE (a franchisor): "FranchisorCosts" -> cost_of_revenue ($3,956,000)

All fallback-only - must never win over a real value the standard concepts already found.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import (
    _CASHFLOW_FIELD_MAPPING,
    _INCOME_FIELD_MAPPING,
    _REVENUE_FALLBACK_ONLY_FIELDS,
    _SBC_BUYBACK_FALLBACK_ONLY_FIELDS,
)

NEW_DIVIDEND_CONCEPTS = [
    "dividends_share_based_compensation_cash",
    "payments_of_distributions_to_affiliates",
    "payments_of_dividends_minority_interest",
    "dividends_common_stock_paidinkind",
]


class TestDividendsPaidFullScan:
    def _make_loader(self, sec_field: str) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_cash_flow"
        loader.period = "annual"
        loader.statement_type = "cashflow"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "dividends_paid", "data_unavailable", "reason"})
        loader._field_mapping = {
            "payments_of_dividends": "dividends_paid",
            sec_field: "dividends_paid",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({sec_field})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mappings_and_fallback_only_wired(self) -> None:
        for sec_field in NEW_DIVIDEND_CONCEPTS:
            assert _CASHFLOW_FIELD_MAPPING[sec_field] == "dividends_paid"
            assert sec_field in _SBC_BUYBACK_FALLBACK_ONLY_FIELDS

    def test_each_concept_fills_empty_dividends_paid(self) -> None:
        for sec_field in NEW_DIVIDEND_CONCEPTS:
            loader = self._make_loader(sec_field)
            row = {"symbol": "TESTCO", "fiscal_year": 2025, sec_field: 12_345.0}

            transformed = loader.transform([row])

            assert transformed[0]["dividends_paid"] == 12_345.0, sec_field

    def test_each_concept_never_overwrites_a_real_dividends_paid_value(self) -> None:
        for sec_field in NEW_DIVIDEND_CONCEPTS:
            loader = self._make_loader(sec_field)
            row = {
                "symbol": "TESTCO",
                "fiscal_year": 2025,
                "payments_of_dividends": 500_000_000.0,
                sec_field: 1.0,
            }

            transformed = loader.transform([row])

            assert transformed[0]["dividends_paid"] == 500_000_000.0, sec_field


class TestFranchisorCostsCostOfRevenue:
    def _make_loader(self) -> SecEdgarStatementLoader:
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

    def test_field_mapping_and_fallback_only_wired(self) -> None:
        assert _INCOME_FIELD_MAPPING["franchisor_costs"] == "cost_of_revenue"
        assert "franchisor_costs" in _REVENUE_FALLBACK_ONLY_FIELDS

    def test_rave_style_franchisor_costs_recovered(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "RAVE", "fiscal_year": 2023, "franchisor_costs": 3_956_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["cost_of_revenue"] == 3_956_000.0

    def test_never_overwrites_a_real_cost_of_revenue_value(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "SOMECORP",
            "fiscal_year": 2025,
            "cost_of_revenue": 500_000_000.0,
            "franchisor_costs": 1.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["cost_of_revenue"] == 500_000_000.0
