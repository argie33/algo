"""Regression test for the 2026-09-08 IFRS "ProfitLossAttributableToOrdinaryEquityHoldersOf
ParentEntity"/"...IncludingDilutiveEffects" aliases (goal session: XBRL coverage-scan backlog
triage, 3rd batch this session).

The candidate triage list flagged this concept as a possible duplicate label for the
already-mapped "ProfitLossAttributableToOwnersOfParent" (target: net_income_loss) - live-
verified via Bank of Nova Scotia's real companyfacts JSON (CIK 0000009631) that this was
WRONG: FY2025 (period end 2025-10-31, 40-F) ProfitLossAttributableToOwnersOfParent=
CAD 7,789,000,000 vs. ProfitLossAttributableToOrdinaryEquityHoldersOfParentEntity=
CAD 7,283,000,000 for the SAME period - a real, material gap (preferred-dividend deduction),
not a relabeled duplicate. It's the genuine IFRS analog of us-gaap's
"NetIncomeLossAvailableToCommonStockholdersBasic" (target: net_income_attributable_to_common).
"""

from typing import Any

from loaders.helpers.financial_statements_income_config import _INCOME_FIELD_MAPPING
from utils.external.sec_income_statement import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000000000"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(year: int, val: float, filed: str, form: str = "40-F") -> dict[str, Any]:
    return {"end": f"{year}-10-31", "val": val, "filed": filed, "fp": "FY", "fy": year, "form": form}


class TestIfrsProfitLossOrdinaryEquityHoldersAlias:
    def test_field_mapping_routes_both_raw_keys_to_the_shared_target_column(self) -> None:
        assert (
            _INCOME_FIELD_MAPPING["profit_loss_attributable_to_ordinary_equity_holders_of_parent_entity"]
            == "net_income_attributable_to_common"
        )
        assert (
            _INCOME_FIELD_MAPPING[
                "profit_loss_attributable_to_ordinary_equity_holders_of_parent_entity_including_dilutive_effects"
            ]
            == "net_income_attributable_to_common"
        )

    def test_not_a_duplicate_of_owners_of_parent(self) -> None:
        # Both concepts present, genuinely different values - net_income_loss and
        # net_income_attributable_to_common must land as two distinct figures, not collapse
        # to the same one.
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "ProfitLossAttributableToOwnersOfParent": {
                    "units": {"USD": [_entry(2025, 7_789_000_000.0, "2025-12-02")]}
                },
                "ProfitLossAttributableToOrdinaryEquityHoldersOfParentEntity": {
                    "units": {"USD": [_entry(2025, 7_283_000_000.0, "2025-12-02")]}
                },
            },
        }
        rows = get_income_statement(_FakeClient(facts), "BNS", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["net_income_loss"] == 7_789_000_000.0
        # get_income_statement() itself returns the raw _to_snake() key - the loader's
        # field_mapping (financial_statements_income_config.py) renames it to
        # "net_income_attributable_to_common" downstream, same as every other alias here.
        assert by_year[2025]["profit_loss_attributable_to_ordinary_equity_holders_of_parent_entity"] == 7_283_000_000.0

    def test_including_dilutive_effects_variant_maps_to_same_target(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "ProfitLossAttributableToOrdinaryEquityHoldersOfParentEntityIncludingDilutiveEffects": {
                    "units": {"USD": [_entry(2025, 7_080_000_000.0, "2026-02-24")]}
                },
            },
        }
        rows = get_income_statement(_FakeClient(facts), "BNS", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert (
            by_year[2025][
                "profit_loss_attributable_to_ordinary_equity_holders_of_parent_entity_including_dilutive_effects"
            ]
            == 7_080_000_000.0
        )
