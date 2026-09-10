"""Regression test (2026-09-07, tie-out check_current_assets_le_total_assets live catch):
SSL (Sasol Ltd, CIK 0000314590, a South African 20-F filer reporting in ZAR) had
annual_balance_sheet.current_assets ~6.4x its own total_assets for FY2022-2025 - a
current_assets/current_liabilities value that was raw, unconverted ZAR sitting in the DB
while total_assets/total_liabilities for the same rows were correctly FX-converted to USD.

Root cause: Sasol's plain ifrs-full:CurrentAssets/CurrentLiabilities concepts (aliased to
assets_current/liabilities_current in _BALANCE_IFRS_ALIASES) have ZERO facts filed after
FY2020 (last: 2020-06-30) - live-confirmed via real SEC companyfacts JSON. From FY2021
onward Sasol splits its balance sheet under IFRS 5 ("non-current assets/disposal groups
held for sale") into "CurrentAssetsOtherThanAssetsOrDisposalGroupsClassifiedAsHeldForSale
OrAsHeldForDistributionToOwners" (current assets excluding the held-for-sale
reclassification) and "CurrentLiabilitiesOtherThanLiabilitiesIncludedInDisposalGroups
ClassifiedAsHeldForSale" instead. Since no alias covered these concept names, every fresh
extraction returned None for assets_current/liabilities_current for FY2021+, and
preserve_on_missing_fields' COALESCE upsert kept whatever raw-ZAR value was already sitting
in the DB from an earlier extraction forever, never getting the real FX-converted figure.

Fixed: added both concepts to _BALANCE_IFRS_ALIASES (fallback-only, listed before the bare
CurrentAssets/CurrentLiabilities aliases so a filer reporting both keeps the bare concept's
value). Live-verified against SSL's real companyfacts JSON: FY2025
CurrentAssetsOtherThan...=ZAR 130,101,000,000, converted at the real 2025-06-30 ZAR/USD rate
(17.78) = ~$7.32B, well under total_assets' ~$20.2B - current_assets <= total_assets holds
again for every affected fiscal year (2021-2025).
"""

from typing import Any

import utils.external.sec_statements as sec_statements_mod
from utils.external.sec_statements import _BALANCE_IFRS_ALIASES, get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000314590"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(end: str, val: float, filed: str, fy: int, form: str = "20-F") -> dict[str, Any]:
    return {"end": end, "val": val, "filed": filed, "fp": "FY", "fy": fy, "form": form}


class TestCurrentAssetsLiabilitiesDisposalGroupAliasesRegistered:
    def test_current_assets_other_than_held_for_sale_alias_registered(self) -> None:
        assert (
            "CurrentAssetsOtherThanAssetsOrDisposalGroupsClassifiedAsHeldForSaleOrAsHeldForDistributionToOwners",
            "assets_current",
        ) in _BALANCE_IFRS_ALIASES

    def test_current_liabilities_other_than_held_for_sale_alias_registered(self) -> None:
        assert (
            "CurrentLiabilitiesOtherThanLiabilitiesIncludedInDisposalGroupsClassifiedAsHeldForSale",
            "liabilities_current",
        ) in _BALANCE_IFRS_ALIASES

    def test_fallback_aliases_listed_after_bare_concept_aliases(self) -> None:
        """First-populated-wins tiebreak (see sec_balance_sheet.py's own comment on this
        ordering): the bare concept must be listed BEFORE its OtherThan-split fallback so
        a filer reporting both for the same fiscal year with an identical (end_date,
        filed_date) - like SSL's own FY2020 - keeps the bare concept's (larger, true total)
        value instead of silently downgrading to the fallback's smaller figure."""
        concepts = [c for c, _ in _BALANCE_IFRS_ALIASES]
        assert concepts.index("CurrentAssets") < concepts.index(
            "CurrentAssetsOtherThanAssetsOrDisposalGroupsClassifiedAsHeldForSaleOrAsHeldForDistributionToOwners"
        )
        assert concepts.index("CurrentLiabilities") < concepts.index(
            "CurrentLiabilitiesOtherThanLiabilitiesIncludedInDisposalGroupsClassifiedAsHeldForSale"
        )


class TestSslCurrentAssetsLiabilitiesRecoveredAndConverted:
    def test_current_assets_recovered_and_fx_converted_when_bare_concept_absent(self, monkeypatch) -> None:
        # SSL's real FY2025 (2025-06-30 fiscal year end) figures, live-confirmed via SEC
        # companyfacts JSON - the bare "CurrentAssets" concept has no fact at all for this
        # year (Sasol stopped tagging it after FY2020).
        monkeypatch.setattr(sec_statements_mod._fx_rate_cache, "get_usd_rate", lambda currency, date_str: 17.78)

        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "Assets": {"units": {"ZAR": [_entry("2025-06-30", 359_555_000_000.0, "2025-08-29", 2025)]}},
                "CurrentAssetsOtherThanAssetsOrDisposalGroupsClassifiedAsHeldForSaleOrAsHeldForDistributionToOwners": {
                    "units": {"ZAR": [_entry("2025-06-30", 130_101_000_000.0, "2025-08-29", 2025)]}
                },
            },
        }

        rows = get_balance_sheet(_FakeClient(facts), "SSL", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        expected_current_assets = 130_101_000_000.0 / 17.78
        assert by_year[2025]["assets_current"] == expected_current_assets
        # The core bug this test guards against: current_assets must never exceed
        # total_assets for the same fiscal year/symbol (check_current_assets_le_total_assets).
        assert by_year[2025]["assets_current"] < by_year[2025]["assets"]

    def test_current_liabilities_recovered_and_fx_converted_when_bare_concept_absent(self, monkeypatch) -> None:
        monkeypatch.setattr(sec_statements_mod._fx_rate_cache, "get_usd_rate", lambda currency, date_str: 17.78)

        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "CurrentLiabilitiesOtherThanLiabilitiesIncludedInDisposalGroupsClassifiedAsHeldForSale": {
                    "units": {"ZAR": [_entry("2025-06-30", 69_436_000_000.0, "2025-08-29", 2025)]}
                },
            },
        }

        rows = get_balance_sheet(_FakeClient(facts), "SSL", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["liabilities_current"] == 69_436_000_000.0 / 17.78

    def test_bare_current_assets_concept_still_wins_when_present(self, monkeypatch) -> None:
        """A filer reporting BOTH the bare concept and the OtherThan fallback for the same
        fiscal year (e.g. SSL's own FY2018-2020 history) must keep the bare concept's value,
        not the fallback."""
        monkeypatch.setattr(sec_statements_mod._fx_rate_cache, "get_usd_rate", lambda currency, date_str: 17.78)

        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "CurrentAssets": {"units": {"ZAR": [_entry("2020-06-30", 177_969_000_000.0, "2020-08-25", 2020)]}},
                "CurrentAssetsOtherThanAssetsOrDisposalGroupsClassifiedAsHeldForSaleOrAsHeldForDistributionToOwners": {
                    "units": {"ZAR": [_entry("2020-06-30", 93_701_000_000.0, "2020-08-25", 2020)]}
                },
            },
        }

        rows = get_balance_sheet(_FakeClient(facts), "SSL", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2020]["assets_current"] == 177_969_000_000.0 / 17.78
