"""Regression test for the 2026-09-16 fix (goal session: SEC-vs-yfinance divergence sweep,
xbrl_yfinance_line_item_report long_term_debt=0-but-real audit): BANR (Banner Corp, a bank
holding company) - real, current annual_balance_sheet row every fiscal year but
long_term_debt=0 while yfinance shows a real $229,151,000 for FY2025.

Live-confirmed via real SEC companyfacts JSON (CIK 0000946673): BANR tags its real
borrowed-funds debt under "AdvancesFromFederalHomeLoanBanks" - FY2025 $150,000,000, 10-K
filed 2026-02-25 - never any of LongTermDebt/NotesPayable/SubordinatedDebt/
OtherLongTermDebt/SecuredLongTermDebt, the concepts this loader already fetched.

Fallback-only (utils/external/sec_balance_sheet.py's get_balance_sheet() comment has the
full live evidence) - must never win over a real value the standard debt concepts already
found.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _BALANCE_FIELD_MAPPING, _DEBT_FALLBACK_ONLY_FIELDS


class TestBanrAdvancesFromFederalHomeLoanBanksFixed:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "long_term_debt", "data_unavailable", "reason"})
        loader._field_mapping = {
            "long_term_debt": "long_term_debt",
            "advances_from_federal_home_loan_banks": "long_term_debt",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"advances_from_federal_home_loan_banks"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_new_concept(self) -> None:
        assert _BALANCE_FIELD_MAPPING["advances_from_federal_home_loan_banks"] == "long_term_debt"
        assert "advances_from_federal_home_loan_banks" in _DEBT_FALLBACK_ONLY_FIELDS

    def test_banr_style_fhlb_advances_recovered(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "BANR", "fiscal_year": 2025, "advances_from_federal_home_loan_banks": 150_000_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 150_000_000.0

    def test_never_overwrites_a_real_long_term_debt_value(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "SOMECORP",
            "fiscal_year": 2025,
            "long_term_debt": 500_000_000.0,
            "advances_from_federal_home_loan_banks": 1.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 500_000_000.0
