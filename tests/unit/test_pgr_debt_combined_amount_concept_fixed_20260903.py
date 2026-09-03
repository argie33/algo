"""Regression test for the 2026-09-03 fix (goal session: "missing SEC/XBRL data under 6k"
sweep, continuation): PGR (Progressive) stopped tagging plain "LongTermDebt" after FY2015 -
every 10-K since tags its real combined debt under "DebtLongtermAndShorttermCombinedAmount"
instead.

Live-confirmed via real SEC companyfacts JSON: $4.899B FY2021 growing to $6.897B FY2025,
continuous and consistent with Progressive's real, publicly known ~$6.9B debt scale - not
debt-free, just a taxonomy switch (same pattern as ADC's DebtInstrumentCarryingAmount switch).
No current/noncurrent split under this concept, so this is fallback-only (must never win over
a real LongTermDebt value from an earlier fiscal year).
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _BALANCE_FIELD_MAPPING, _DEBT_FALLBACK_ONLY_FIELDS


class TestPgrDebtCombinedAmountConceptFixed:
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
            "debt_longterm_and_shortterm_combined_amount": "long_term_debt",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"debt_longterm_and_shortterm_combined_amount"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_combined_amount_to_long_term_debt(self) -> None:
        assert _BALANCE_FIELD_MAPPING["debt_longterm_and_shortterm_combined_amount"] == "long_term_debt"
        assert "debt_longterm_and_shortterm_combined_amount" in _DEBT_FALLBACK_ONLY_FIELDS

    def test_pgr_style_debt_recovered_when_no_other_concept_present(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "PGR",
            "fiscal_year": 2025,
            "debt_longterm_and_shortterm_combined_amount": 6_897_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 6_897_000_000.0

    def test_combined_amount_never_overwrites_a_real_long_term_debt_value(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "AAPL",
            "fiscal_year": 2025,
            "long_term_debt": 95_281_000_000.0,
            "debt_longterm_and_shortterm_combined_amount": 1.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 95_281_000_000.0
