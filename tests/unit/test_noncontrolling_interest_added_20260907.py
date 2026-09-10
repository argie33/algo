"""Regression test for the 2026-09-07 fix (goal session: check_balance_sheet_identity NCI gap
rootcaused, migration 1265): "MinorityInterest" is tagged by large filers with material
noncontrolling interests (XOM, CVX, KKR, APO, etc.) but had no noncontrolling_interest-shaped
column anywhere in the schema - this was the root cause of 761/5,078 (15%) of the annual
universe failing check_balance_sheet_identity's assets == liabilities + stockholders_equity
identity, since this schema's stockholders_equity column stores the narrower parent-only
concept.

Live-confirmed via real companyfacts JSON: XOM FY2009 (period end 2009-12-31)
MinorityInterest = $4,823,000,000, which exactly closes the gap between assets
($233,323,000,000) and liabilities ($117,931,000,000) + stockholders_equity
($110,569,000,000).
"""

from typing import Any

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _BALANCE_FIELD_MAPPING
from utils.external.sec_balance_sheet import get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000000000"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(year: int, val: float, filed: str, form: str = "10-K") -> dict[str, Any]:
    return {"end": f"{year}-12-31", "val": val, "filed": filed, "fp": "FY", "fy": year, "form": form}


class TestMinorityInterestWired:
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
            "minority_interest": "noncontrolling_interest",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_minority_interest(self) -> None:
        assert _BALANCE_FIELD_MAPPING["minority_interest"] == "noncontrolling_interest"

    def test_xom_style_minority_interest_recovered(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "XOM", "fiscal_year": 2009, "minority_interest": 4_823_000_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["noncontrolling_interest"] == 4_823_000_000.0

    def test_xom_style_minority_interest_maps_through_get_balance_sheet(self) -> None:
        facts = {
            "us-gaap": {
                "MinorityInterest": {"units": {"USD": [_entry(2009, 4_823_000_000.0, "2010-02-26")]}},
            },
            "ifrs-full": {},
        }
        rows = get_balance_sheet(_FakeClient(facts), "XOM", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2009]["minority_interest"] == 4_823_000_000.0

    def test_xom_style_identity_closes_with_nci(self) -> None:
        assets = 233_323_000_000.0
        liabilities = 117_931_000_000.0
        stockholders_equity = 110_569_000_000.0
        nci = 4_823_000_000.0

        assert assets == liabilities + stockholders_equity + nci
