"""Regression test for adding ifrs-full:NoncurrentAssetsOrDisposalGroupsClassifiedAsHeldForSale
to _BALANCE_IFRS_ALIASES (utils/external/sec_balance_sheet.py), found via the 2026-09-09
xbrl_concept_coverage_scan.py comment-leak fix (see
test_xbrl_concept_coverage_comment_leak_20260909.py) - 101 real filers tag this concept
(scan-confirmed post-fix), and the codebase's own comment on the sibling
"CurrentAssetsOtherThan..." concept (see test_ssl_current_assets_liabilities_disposal_group_split_
20260907.py) already documented it as the real held-for-sale component this loader has "no
summing mechanism" for.

This is a fallback-only, non-summing addition: listed LAST among the current-assets concepts so
first-populated-wins (_aggregate_concepts_should_replace_entry) means it only ever fills
assets_current when it is otherwise completely empty for that period - it never partially
overwrites or sums against the "OtherThan..." figure when a filer tags both (live-confirmed via
the real companyfacts cache that several filers, e.g. Korea Electric Power/Brookfield/National
Grid/GSK, tag IDENTICAL values under both concepts for the same period - summing those would
double-count). It deliberately does NOT close the real partial-figure gap for filers that tag
both concepts as genuinely separate non-overlapping pieces (e.g. YPF 2017: HeldForSale=$8.823B
vs OtherThan=$43M) - that would require an actual summing feature, out of scope here.
"""

from typing import Any

import utils.external.sec_statements as sec_statements_mod
from utils.external.sec_statements import _BALANCE_IFRS_ALIASES, get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000016859"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(end: str, val: float, filed: str, fy: int, form: str = "20-F") -> dict[str, Any]:
    return {"end": end, "val": val, "filed": filed, "fp": "FY", "fy": fy, "form": form}


class TestHeldForSaleAliasRegistered:
    def test_alias_registered(self) -> None:
        assert (
            "NoncurrentAssetsOrDisposalGroupsClassifiedAsHeldForSale",
            "assets_current",
        ) in _BALANCE_IFRS_ALIASES

    def test_listed_after_bare_and_other_than_concepts(self) -> None:
        """First-populated-wins tiebreak: this fallback must be listed AFTER both the bare
        "CurrentAssets" concept and the "OtherThan..." concept so a filer reporting any of
        those keeps their (larger, more complete) value instead of this narrower component."""
        concepts = [c for c, _ in _BALANCE_IFRS_ALIASES]
        assert concepts.index("CurrentAssets") < concepts.index(
            "NoncurrentAssetsOrDisposalGroupsClassifiedAsHeldForSale"
        )
        assert concepts.index(
            "CurrentAssetsOtherThanAssetsOrDisposalGroupsClassifiedAsHeldForSaleOrAsHeldForDistributionToOwners"
        ) < concepts.index("NoncurrentAssetsOrDisposalGroupsClassifiedAsHeldForSale")


class TestHeldForSaleFillsOnlyWhenNothingElsePresent:
    def test_fills_assets_current_when_no_other_concept_present(self, monkeypatch) -> None:
        """A filer tagging ONLY the held-for-sale component (no bare CurrentAssets, no
        OtherThan...) previously got NULL assets_current despite real data being present."""
        monkeypatch.setattr(sec_statements_mod._fx_rate_cache, "get_usd_rate", lambda currency, date_str: 1.0)

        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "Assets": {"units": {"USD": [_entry("2025-12-31", 500_000_000.0, "2026-03-01", 2025)]}},
                "NoncurrentAssetsOrDisposalGroupsClassifiedAsHeldForSale": {
                    "units": {"USD": [_entry("2025-12-31", 8_823_000.0, "2026-03-01", 2025)]}
                },
            },
        }

        rows = get_balance_sheet(_FakeClient(facts), "TEST", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["assets_current"] == 8_823_000.0

    def test_never_overwrites_other_than_concept_when_both_present(self, monkeypatch) -> None:
        """Common real-world case (confirmed via cache): a filer tags both concepts for the
        same period. The larger "OtherThan..." figure (listed first) must win - this fallback
        must never sum with it or overwrite it, to avoid double-counting."""
        monkeypatch.setattr(sec_statements_mod._fx_rate_cache, "get_usd_rate", lambda currency, date_str: 1.0)

        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "CurrentAssetsOtherThanAssetsOrDisposalGroupsClassifiedAsHeldForSaleOrAsHeldForDistributionToOwners": {
                    "units": {"USD": [_entry("2025-12-31", 130_101_000.0, "2026-03-01", 2025)]}
                },
                "NoncurrentAssetsOrDisposalGroupsClassifiedAsHeldForSale": {
                    "units": {"USD": [_entry("2025-12-31", 53_000.0, "2026-03-01", 2025)]}
                },
            },
        }

        rows = get_balance_sheet(_FakeClient(facts), "TEST", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["assets_current"] == 130_101_000.0

    def test_never_overwrites_bare_current_assets_when_present(self, monkeypatch) -> None:
        monkeypatch.setattr(sec_statements_mod._fx_rate_cache, "get_usd_rate", lambda currency, date_str: 1.0)

        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "CurrentAssets": {"units": {"USD": [_entry("2025-12-31", 200_000_000.0, "2026-03-01", 2025)]}},
                "NoncurrentAssetsOrDisposalGroupsClassifiedAsHeldForSale": {
                    "units": {"USD": [_entry("2025-12-31", 53_000.0, "2026-03-01", 2025)]}
                },
            },
        }

        rows = get_balance_sheet(_FakeClient(facts), "TEST", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["assets_current"] == 200_000_000.0
