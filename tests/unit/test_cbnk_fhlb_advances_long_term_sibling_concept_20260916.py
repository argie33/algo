"""Regression test for the 2026-09-16 follow-up fix (same sweep as
test_banr_advances_from_federal_home_loan_banks_fixed_20260916.py): CBNK (Capital Bancorp)
and MYFW (Mid-Southern Savings), both bank holding companies, tag their real borrowed-funds
debt under "FederalHomeLoanBankAdvancesLongTerm" - a DIFFERENT XBRL concept from
"AdvancesFromFederalHomeLoanBanks" the BANR fix added.

Live-confirmed via real SEC companyfacts JSON: CBNK (CIK 0001419536) FY2025 $50,000,000,
MYFW (CIK 0001327607) FY2024 $10,000,000 - neither ever tags
AdvancesFromFederalHomeLoanBanks or any of the standard debt concepts, which is why
long_term_debt sat at 0 for every fiscal year despite yfinance showing the real figure.

Fallback-only (utils/external/sec_balance_sheet.py's get_balance_sheet() comment has the
full live evidence) - must never win over a real value the standard debt concepts already
found.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _BALANCE_FIELD_MAPPING, _DEBT_FALLBACK_ONLY_FIELDS


class TestCbnkFhlbAdvancesLongTermSiblingConcept:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "long_term_debt", "data_unavailable", "reason"})
        loader._field_mapping = {
            "long_term_debt": "long_term_debt",
            "federal_home_loan_bank_advances_long_term": "long_term_debt",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"federal_home_loan_bank_advances_long_term"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_new_concept(self) -> None:
        assert _BALANCE_FIELD_MAPPING["federal_home_loan_bank_advances_long_term"] == "long_term_debt"
        assert "federal_home_loan_bank_advances_long_term" in _DEBT_FALLBACK_ONLY_FIELDS

    def test_cbnk_style_fhlb_advances_recovered(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "CBNK", "fiscal_year": 2025, "federal_home_loan_bank_advances_long_term": 50_000_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 50_000_000.0

    def test_never_overwrites_a_real_long_term_debt_value(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "SOMECORP",
            "fiscal_year": 2025,
            "long_term_debt": 500_000_000.0,
            "federal_home_loan_bank_advances_long_term": 1.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 500_000_000.0
