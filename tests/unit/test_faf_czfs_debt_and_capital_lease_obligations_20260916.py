"""Regression test for the 2026-09-16 fix (goal: SEC-vs-yfinance divergence sweep,
our_value=0-vs-real-yfinance-value audit): FAF (First American Financial) and CZFS
(Citizens Financial Services) both tag their real combined debt-plus-lease total under
"DebtAndCapitalLeaseObligations" (no "LongTerm" prefix - a distinct concept from the
already-fetched "LongTermDebtAndCapitalLeaseObligations") - live-confirmed via real SEC
companyfacts JSON: FAF $1,545,400,000 FY2025, exactly matching the yfinance-flagged value.
Never previously fetched at all, so both symbols fell into the "structurally debt-free"
bucket despite carrying real, material debt.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _BALANCE_FIELD_MAPPING, _DEBT_FALLBACK_ONLY_FIELDS


class TestFafCzfsDebtAndCapitalLeaseObligationsFixed:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset(
            {"symbol", "fiscal_year", "long_term_debt", "short_term_debt", "data_unavailable", "reason"}
        )
        loader._field_mapping = {
            "long_term_debt": "long_term_debt",
            "debt_and_capital_lease_obligations": "long_term_debt",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"debt_and_capital_lease_obligations"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_debt_and_capital_lease_obligations(self) -> None:
        assert _BALANCE_FIELD_MAPPING["debt_and_capital_lease_obligations"] == "long_term_debt"
        assert "debt_and_capital_lease_obligations" in _DEBT_FALLBACK_ONLY_FIELDS

    def test_faf_style_debt_recovered_when_no_other_concept_present(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "FAF",
            "fiscal_year": 2025,
            "debt_and_capital_lease_obligations": 1_545_400_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 1_545_400_000.0

    def test_never_overwrites_a_real_long_term_debt_value(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "TEST",
            "fiscal_year": 2025,
            "long_term_debt": 95_281_000_000.0,
            "debt_and_capital_lease_obligations": 1.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 95_281_000_000.0
