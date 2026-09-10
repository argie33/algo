"""Regression test for the 2026-09-08 IFRS "WeightedAverageShares"/
"DepreciationPropertyPlantAndEquipment"/"AmortisationIntangibleAssetsOtherThanGoodwill"/
"AdministrativeExpense" aliases (goal session: XBRL coverage-scan backlog triage, follow-up to
the same day's Borrowings/NoncontrollingInterests and TradeReceivables/TradeAndOtherCurrent
Payables/DepreciationAndAmortisationExpense alias passes).

"WeightedAverageShares" - live-confirmed via Agnico Eagle's real companyfacts JSON (CIK
0000002809, ifrs-full-only): FY2025 WeightedAverageShares=501,993,000 shares, a sane real
share count for a ~$50B market-cap miner.

"DepreciationPropertyPlantAndEquipment" - live-confirmed via Barrick Mining Corp's real
companyfacts JSON (CIK 0000756894): FY2023 DepreciationPropertyPlantAndEquipment=
USD 2,045,000,000, ~18% of that year's Revenue (USD 11,397,000,000) - a sane depreciation
ratio for a capital-intensive miner.

"AmortisationIntangibleAssetsOtherThanGoodwill" - live-confirmed via PLDT's real companyfacts
JSON (CIK 0000078150): FY2022=PHP 228,000,000, a small, plausible fraction of PLDT's own
separately-tagged total D&A (DepreciationAndAmortisationExpense=PHP 98,631-98,714M for the
same period) - sane for a telecom whose D&A is dominated by network PP&E depreciation.

"AdministrativeExpense" - live-confirmed via Barrick Mining Corp and Methanex Corporation
(CIK 0000886977), both of which tag ONLY this concept with no separate selling/distribution/
marketing expense concept anywhere in their real companyfacts JSON, and via Smith & Nephew plc
(CIK 0000845982, a medtech filer with a real sales force) showing the same pattern - in every
filer checked, this functions as the filer's complete SG&A-equivalent total.
"""

from typing import Any

from utils.external.sec_income_statement import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000000000"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(year: int, val: float, filed: str, form: str = "20-F", end: str | None = None) -> dict[str, Any]:
    return {
        "end": end or f"{year}-12-31",
        "val": val,
        "filed": filed,
        "fp": "FY",
        "fy": year,
        "form": form,
    }


class TestIfrsWeightedAverageSharesAlias:
    # get_income_statement() returns the raw target_key ("weighted_average_number_of_shares_
    # outstanding_basic") - the loaders/load_financial_statements.py field_mapping step (not
    # exercised by this extraction-layer test) is what routes it downstream to the
    # shares_outstanding_basic DB column, same convention as this repo's other extraction-
    # layer alias tests asserting raw target keys.
    def test_maps_to_weighted_average_number_of_shares_outstanding_basic(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "WeightedAverageShares": {
                    "units": {"shares": [_entry(2025, 501_993_000.0, "2026-02-20", form="40-F")]}
                },
            },
        }
        rows = get_income_statement(_FakeClient(facts), "AEM", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["weighted_average_number_of_shares_outstanding_basic"] == 501_993_000.0

    def test_us_gaap_concept_wins_over_ifrs_fallback(self) -> None:
        # A filer reporting the real us-gaap weighted-average keeps that value - the ifrs
        # alias never overwrites it (gaap-source specs are processed first).
        facts = {
            "us-gaap": {
                "WeightedAverageNumberOfSharesOutstandingBasic": {
                    "units": {"shares": [_entry(2025, 10_000_000.0, "2026-02-20", form="10-K")]}
                },
            },
            "ifrs-full": {
                "WeightedAverageShares": {
                    "units": {"shares": [_entry(2025, 999_999_999.0, "2026-02-20", form="40-F")]}
                },
            },
        }
        rows = get_income_statement(_FakeClient(facts), "DUAL", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["weighted_average_number_of_shares_outstanding_basic"] == 10_000_000.0


class TestIfrsDepreciationPropertyPlantAndEquipmentAlias:
    def test_maps_to_depreciation(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "DepreciationPropertyPlantAndEquipment": {
                    "units": {"USD": [_entry(2023, 2_045_000_000.0, "2024-02-15", form="40-F")]}
                },
            },
        }
        rows = get_income_statement(_FakeClient(facts), "GOLD", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2023]["depreciation"] == 2_045_000_000.0


class TestIfrsAmortisationIntangibleAssetsOtherThanGoodwillAlias:
    def test_maps_to_amortization_of_intangible_assets(self) -> None:
        # Real PLDT filings tag this in PHP (see the live-evidence comment on the alias
        # itself); USD is used here so the assertion checks the raw aliasing/mapping logic
        # without also exercising FX-rate lookups (PHP is a MAJOR_CURRENCIES entry subject
        # to live conversion, which a _FakeClient-based unit test shouldn't depend on).
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "AmortisationIntangibleAssetsOtherThanGoodwill": {
                    "units": {"USD": [_entry(2022, 228_000_000.0, "2023-04-01", form="20-F")]}
                },
            },
        }
        rows = get_income_statement(_FakeClient(facts), "PHI", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2022]["amortization_of_intangible_assets"] == 228_000_000.0


class TestIfrsAdministrativeExpenseAlias:
    def test_maps_to_selling_general_and_administrative_expense(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "AdministrativeExpense": {"units": {"USD": [_entry(2023, 101_000_000.0, "2024-02-15", form="40-F")]}},
            },
        }
        rows = get_income_statement(_FakeClient(facts), "GOLD", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2023]["selling_general_and_administrative_expense"] == 101_000_000.0

    def test_selling_general_and_administrative_expense_wins_over_administrative_fallback(self) -> None:
        # A filer reporting the real combined us-gaap SG&A total keeps that value - the
        # narrower "administrative"-only ifrs alias never overwrites it.
        facts = {
            "us-gaap": {
                "SellingGeneralAndAdministrativeExpense": {
                    "units": {"USD": [_entry(2023, 500_000_000.0, "2024-02-15", form="10-K")]}
                },
            },
            "ifrs-full": {
                "AdministrativeExpense": {"units": {"USD": [_entry(2023, 101_000_000.0, "2024-02-15", form="40-F")]}},
            },
        }
        rows = get_income_statement(_FakeClient(facts), "DUAL2", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2023]["selling_general_and_administrative_expense"] == 500_000_000.0
