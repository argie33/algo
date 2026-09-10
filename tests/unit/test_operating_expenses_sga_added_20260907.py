"""Regression test for the 2026-09-07 fix (goal session: XBRL concept coverage scanner
follow-up, migration 1264): "SellingGeneralAndAdministrativeExpense" was tagged by 2,820+ real
filers but had no operating_expenses/SG&A-shaped column anywhere in the schema - found via
scripts/xbrl_concept_coverage_scan.py's systematic gap scan.

Live-confirmed via real companyfacts JSON: WMT FY2026 (period end 2026-01-31) =
$147,943,000,000, TGT FY2026 (period end 2026-01-31) = $21,535,000,000 - both sane SG&A
figures relative to revenue.
"""

from typing import Any

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _INCOME_FIELD_MAPPING
from utils.external.sec_income_statement import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000000000"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(year: int, val: float, filed: str, form: str = "10-K") -> dict[str, Any]:
    return {"end": f"{year}-12-31", "val": val, "filed": filed, "fp": "FY", "fy": year, "form": form}


class TestSellingGeneralAndAdministrativeExpenseWired:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "operating_expenses", "data_unavailable", "reason"})
        loader._field_mapping = {
            "operating_expenses": "operating_expenses",
            "selling_general_and_administrative_expense": "operating_expenses",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_selling_general_and_administrative_expense(self) -> None:
        assert _INCOME_FIELD_MAPPING["selling_general_and_administrative_expense"] == "operating_expenses"

    def test_wmt_style_operating_expenses_recovered(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "WMT", "fiscal_year": 2026, "selling_general_and_administrative_expense": 147_943_000_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["operating_expenses"] == 147_943_000_000.0

    def test_tgt_style_operating_expenses_recovered(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "TGT", "fiscal_year": 2026, "selling_general_and_administrative_expense": 21_535_000_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["operating_expenses"] == 21_535_000_000.0

    def test_wmt_style_operating_expenses_maps_through_get_income_statement(self) -> None:
        facts = {
            "us-gaap": {
                "SellingGeneralAndAdministrativeExpense": {
                    "units": {"USD": [_entry(2026, 147_943_000_000.0, "2026-03-20")]}
                },
            },
            "ifrs-full": {},
        }
        rows = get_income_statement(_FakeClient(facts), "WMT", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2026]["selling_general_and_administrative_expense"] == 147_943_000_000.0


class TestGeneralAndAdministrativeExpenseFallback:
    """Regression tests for the 2026-09-09 fix (goal: XBRL coverage-scan comment-leak
    follow-up): "GeneralAndAdministrativeExpense" (us-gaap and ifrs-full) had been quoted only
    in a comment on the SellingGeneralAndAdministrativeExpense entry above ("none of the 4
    filers checked tag 'GeneralAndAdministrativeExpense'") - a comment-leak bug in
    scripts/xbrl_concept_coverage_scan.py's load_known_concepts() made that mention alone look
    like a real fetch, hiding a genuine ~3,057-filer gap (2,231 us-gaap + 276 ifrs-full on the
    local companyfacts cache) from every later scan.

    See _fill_sga_from_general_and_administrative_when_no_selling_component() in
    sec_income_statement_fallbacks.py for the live BOEING/MASTEC (no separate selling tag, safe
    to alias) vs. Arts Way Manufacturing-style (G&A AND SellingExpense both tagged separately,
    NOT safe to alias G&A alone) evidence this fallback is built around.
    """

    def test_general_and_administrative_used_when_no_sga_and_no_selling_component(self) -> None:
        # BOEING-style: G&A tagged, no combined SG&A, no separate selling/marketing/
        # distribution concept - G&A genuinely is the complete SG&A-equivalent here.
        facts = {
            "us-gaap": {
                "GeneralAndAdministrativeExpense": {"units": {"USD": [_entry(2025, 6_090_000_000.0, "2026-01-28")]}},
            },
            "ifrs-full": {},
        }
        rows = get_income_statement(_FakeClient(facts), "BA", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["selling_general_and_administrative_expense"] == 6_090_000_000.0

    def test_general_and_administrative_not_used_when_selling_expense_also_tagged(self) -> None:
        # ARTS WAY MANUFACTURING-style: G&A AND a separate SellingExpense are BOTH tagged with
        # no combined SG&A total - using G&A alone would understate true combined SG&A, so this
        # fallback must NOT fire; "selling_general_and_administrative_expense" stays unset.
        facts = {
            "us-gaap": {
                "GeneralAndAdministrativeExpense": {"units": {"USD": [_entry(2025, 4_193_753.0, "2026-01-15")]}},
                "SellingExpense": {"units": {"USD": [_entry(2025, 1_439_529.0, "2026-01-15")]}},
            },
            "ifrs-full": {},
        }
        rows = get_income_statement(_FakeClient(facts), "ARTW", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025].get("selling_general_and_administrative_expense") is None
        # Never leaks the raw unmapped gate keys into the final row either.
        assert "general_and_administrative_expense" not in by_year[2025]
        assert "selling_expense" not in by_year[2025]

    def test_general_and_administrative_never_overwrites_real_combined_sga(self) -> None:
        # A filer that DOES tag the combined concept keeps that value - G&A (if also present,
        # e.g. a restated/duplicate tag) is never allowed to clobber the real combined total.
        facts = {
            "us-gaap": {
                "SellingGeneralAndAdministrativeExpense": {
                    "units": {"USD": [_entry(2025, 147_943_000_000.0, "2026-03-20")]}
                },
                "GeneralAndAdministrativeExpense": {"units": {"USD": [_entry(2025, 1_000_000_000.0, "2026-03-20")]}},
            },
            "ifrs-full": {},
        }
        rows = get_income_statement(_FakeClient(facts), "WMT", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["selling_general_and_administrative_expense"] == 147_943_000_000.0

    def test_ifrs_full_general_and_administrative_used_when_no_administrative_or_selling(self) -> None:
        # WPP-style: ifrs-full GeneralAndAdministrativeExpense tagged, no AdministrativeExpense,
        # no separate selling-type concept - safe to alias directly.
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "GeneralAndAdministrativeExpense": {"units": {"USD": [_entry(2025, 1_764_000_000.0, "2026-02-28")]}},
            },
        }
        rows = get_income_statement(_FakeClient(facts), "WPP", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["selling_general_and_administrative_expense"] == 1_764_000_000.0

    def test_ifrs_full_general_and_administrative_not_used_when_distribution_costs_also_tagged(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "GeneralAndAdministrativeExpense": {"units": {"EUR": [_entry(2025, 100_000_000.0, "2026-02-28")]}},
                "DistributionCosts": {"units": {"EUR": [_entry(2025, 50_000_000.0, "2026-02-28")]}},
            },
        }
        rows = get_income_statement(_FakeClient(facts), "TESTIFRS", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025].get("selling_general_and_administrative_expense") is None
