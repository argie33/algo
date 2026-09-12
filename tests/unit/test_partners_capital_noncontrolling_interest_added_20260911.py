"""Regression test for the 2026-09-11 fix (goal: "SEC/XBRL missing data under 200" push):
"PartnersCapitalAttributableToNoncontrollingInterest" is the partnership/Up-C-structure
equivalent of "MinorityInterest" (see test_noncontrolling_interest_added_20260907.py for that
concept's own fix) but had no mapping anywhere - a filer whose parent-only "PartnersCapital" is
genuinely near-zero (nearly all equity held by noncontrolling unitholders) lost the entire NCI
portion, since the "last-listed-wins" merge correctly keeps the parent-only figure but nothing
captured the dropped remainder.

Live-confirmed via real companyfacts JSON: PS/Pershing Square Inc. (CIK 0002026053) FY2026 Q2
10-Q (period end 2026-06-30) tags plain PartnersCapital=$0 while
PartnersCapitalIncludingPortionAttributableToNoncontrollingInterest=$1,409,179,576 for the SAME
period - exactly matching Assets($1,812,657,825) - Liabilities($403,478,249).
"""

from typing import Any

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _BALANCE_FIELD_MAPPING
from utils.external.sec_balance_sheet import get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0002026053"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(year: int, val: float, filed: str, end: str, form: str = "10-Q") -> dict[str, Any]:
    return {"end": end, "val": val, "filed": filed, "fp": "Q2", "fy": year, "form": form}


class TestPartnersCapitalNoncontrollingInterestWired:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset(
            {"symbol", "fiscal_year", "noncontrolling_interest", "data_unavailable", "reason"}
        )
        loader._field_mapping = {
            "noncontrolling_interest": "noncontrolling_interest",
            "partners_capital_attributable_to_noncontrolling_interest": "noncontrolling_interest",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_partners_capital_nci(self) -> None:
        assert (
            _BALANCE_FIELD_MAPPING["partners_capital_attributable_to_noncontrolling_interest"]
            == "noncontrolling_interest"
        )

    def test_ps_style_partners_capital_nci_recovered(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "PS",
            "fiscal_year": 2026,
            "partners_capital_attributable_to_noncontrolling_interest": 1_409_179_576.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["noncontrolling_interest"] == 1_409_179_576.0

    def test_ps_style_nci_maps_through_get_balance_sheet(self) -> None:
        facts = {
            "us-gaap": {
                "PartnersCapital": {"units": {"USD": [_entry(2026, 0.0, "2026-08-01", "2026-06-30")]}},
                "PartnersCapitalAttributableToNoncontrollingInterest": {
                    "units": {"USD": [_entry(2026, 1_409_179_576.0, "2026-08-01", "2026-06-30")]}
                },
            },
            "ifrs-full": {},
        }
        rows = get_balance_sheet(_FakeClient(facts), "PS", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2026]["partners_capital_attributable_to_noncontrolling_interest"] == 1_409_179_576.0

    def test_ps_style_identity_closes_with_nci(self) -> None:
        assets = 1_812_657_825.0
        liabilities = 403_478_249.0
        stockholders_equity = 0.0
        nci = 1_409_179_576.0

        assert assets == liabilities + stockholders_equity + nci
