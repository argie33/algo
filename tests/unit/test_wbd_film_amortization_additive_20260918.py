"""Regression test for the 2026-09-18 fix (goal session: data-issue reduction): WBD (Warner
Bros Discovery) tags real, nonzero "FilmMonetizedInFilmGroupAmortizationExpense" AND
"FilmMonetizedOnItsOwnAmortizationExpense" (ASC 926 film-cost amortization for media/content
companies) every fiscal year, genuinely additive to depreciation_expense/amortization_expense,
not alternates - live-confirmed via real SEC companyfacts JSON, FY2023: combined
depreciation ($1,097,000,000) + AmortizationOfIntangibleAssets ($6,854,000,000) +
FilmMonetizedInFilmGroupAmortizationExpense ($10,648,000,000) +
FilmMonetizedOnItsOwnAmortizationExpense ($5,165,000,000) = $23,764,000,000, within 1% of the
yfinance-flagged $24,009,000,000.

Before this fix, our stored depreciation_expense+amortization_expense for WBD was only
$7,951,000,000 (missing the two film concepts entirely) - not a bug in the crosscheck's own
depreciation+amortization composite-sum logic (scripts/xbrl_yfinance_crosscheck.py's
_COMPOSITE_SUM_FIELDS), but a genuine missing-concept extraction gap for media/content filers.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _INCOME_FIELD_MAPPING


class TestWbdFilmAmortizationAdditive:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "amortization_expense", "data_unavailable", "reason"})
        loader._field_mapping = {
            "amortization_of_intangible_assets": "amortization_expense",
            "film_monetized_in_film_group_amortization_expense": "amortization_expense",
            "film_monetized_on_its_own_amortization_expense": "amortization_expense",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wired(self) -> None:
        assert _INCOME_FIELD_MAPPING["film_monetized_in_film_group_amortization_expense"] == "amortization_expense"
        assert _INCOME_FIELD_MAPPING["film_monetized_on_its_own_amortization_expense"] == "amortization_expense"

    def test_wbd_style_three_concepts_summed_not_overwritten(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "WBD",
            "fiscal_year": 2023,
            "amortization_of_intangible_assets": 6_854_000_000.0,
            "film_monetized_in_film_group_amortization_expense": 10_648_000_000.0,
            "film_monetized_on_its_own_amortization_expense": 5_165_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["amortization_expense"] == 22_667_000_000.0

    def test_solo_film_concept_still_fills_empty_field(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "SOMEMEDIACORP",
            "fiscal_year": 2025,
            "film_monetized_on_its_own_amortization_expense": 5_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["amortization_expense"] == 5_000.0
