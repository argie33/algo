"""Regression test for the 2026-09-03 fix (goal session: "missing SEC/XBRL data under 6k"
sweep, total_debt_not_itemized investigation): mortgage REITs finance almost entirely via
repurchase ("repo") agreements, a standard, companyfacts-exposed us-gaap concept
("SecuritiesSoldUnderAgreementsToRepurchase") none of the LongTermDebt/CommercialPaper/
DebtCurrent/etc. concepts already fetched ever captured.

Live-confirmed via real SEC companyconcept API data: AGNC Investment Corp (CIK 0001423689)
$60,798,000,000 FY2024/$50,426,000,000 FY2023, ARMOUR Residential REIT (CIK 0001428205)
$10,713,830,000 FY2024/$9,647,982,000 FY2023 - both real, massive, and completely invisible
to long_term_debt/short_term_debt before this fix (every fiscal year NULL for all 4 debt-
component columns in annual_balance_sheet despite each being a multi-billion-dollar
leveraged mortgage REIT). Repo agreements are short-duration rolling financing, so this
targets short_term_debt, same semantic class as CommercialPaper/ShortTermBorrowings.
Fallback-only since a filer reporting a more specific standard debt concept must always
keep that value - live-checked neither AGNC nor ARR reports any other debt concept, so no
overwrite-collision risk for the two symbols this was found from.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _BALANCE_FIELD_MAPPING, _DEBT_FALLBACK_ONLY_FIELDS


class TestAgncArrRepoAgreementDebtConceptFixed:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset(
            {"symbol", "fiscal_year", "long_term_debt", "short_term_debt", "data_unavailable", "reason"}
        )
        loader._field_mapping = {
            "short_term_debt": "short_term_debt",
            "commercial_paper": "short_term_debt",
            "securities_sold_under_agreements_to_repurchase": "short_term_debt",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"securities_sold_under_agreements_to_repurchase"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_repo_agreement_concept_to_short_term_debt(self) -> None:
        assert _BALANCE_FIELD_MAPPING["securities_sold_under_agreements_to_repurchase"] == "short_term_debt"
        assert "securities_sold_under_agreements_to_repurchase" in _DEBT_FALLBACK_ONLY_FIELDS

    def test_agnc_style_repo_debt_recovered_when_no_other_concept_present(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "AGNC",
            "fiscal_year": 2024,
            "securities_sold_under_agreements_to_repurchase": 60_798_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["short_term_debt"] == 60_798_000_000.0

    def test_arr_style_repo_debt_recovered_when_no_other_concept_present(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "ARR",
            "fiscal_year": 2024,
            "securities_sold_under_agreements_to_repurchase": 10_713_830_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["short_term_debt"] == 10_713_830_000.0

    def test_never_overwrites_a_real_short_term_debt_value(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "AAPL",
            "fiscal_year": 2025,
            "commercial_paper": 7_980_000_000.0,
            "securities_sold_under_agreements_to_repurchase": 1.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["short_term_debt"] == 7_980_000_000.0
