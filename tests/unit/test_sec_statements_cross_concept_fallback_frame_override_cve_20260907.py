"""Regression test for a cross-concept collision bug in
_aggregate_concepts_should_replace_entry() (utils/external/sec_statements_entry_resolution.py):

Live-verified 2026-09-07 via Cenovus Energy (CVE, CIK 0001475260) real SEC companyfacts JSON:
sec_balance_sheet.py's _BALANCE_IFRS_ALIASES lists two concepts that both target the
"assets_current" column - the primary "CurrentAssets" concept, and a fallback,
"CurrentAssetsOtherThanAssetsOrDisposalGroupsClassifiedAsHeldForSaleOrAsHeldForDistribution
ToOwners", meant only for filers whose bare CurrentAssets concept has no fact at all.

For CVE FY2022 (end=2022-12-31, accn 0001475260-23-000015, filed 2023-02-16, both from the
SAME 40-F), the primary CurrentAssets concept correctly reports val=12,430,000,000 CAD with
no frame key, while the fallback concept's same-accn/same-filed/same-end_date fact reports
val=0 but DOES carry SEC's frame="CY2022Q4I" tag. The old frame-preference tiebreak (built
for PMT/IPAR - same-concept multi-fact collisions) let the fallback's frame-tagged 0
overwrite the primary concept's already-correct $12.43B, producing current_assets=0.00 for
FY2022 while every other field on the row (total_assets, inventory, cash_and_equivalents)
stayed normal-scale.

Fixed by tracking which concept last populated each column and requiring an exact concept
match before falling through to the same-rank/same-instant frame/end-date tiebreak
refinements - first-populated-wins for cross-concept collisions. A fallback concept can
still populate a genuinely EMPTY column (the documented, intended use case), just never
override an already-populated primary concept's value via this tiebreak.
"""

from utils.external.sec_balance_sheet import get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0001475260"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    # USD (not CVE's real CAD) so this test exercises concept-selection in isolation,
    # without depending on a live FX-rate lookup for the currency-conversion path.
    return {"units": {"USD": entries}}


_CVE_PRIMARY_CURRENT_ASSETS = [
    {
        "end": "2022-12-31",
        "val": 12_430_000_000,
        "accn": "0001475260-23-000015",
        "fy": 2022,
        "fp": "FY",
        "form": "40-F",
        "filed": "2023-02-16",
    },
]

_CVE_FALLBACK_CURRENT_ASSETS_EXCL_HFS = [
    {
        "end": "2022-12-31",
        "val": 0,
        "accn": "0001475260-23-000015",
        "fy": 2022,
        "fp": "FY",
        "form": "40-F",
        "filed": "2023-02-16",
        "frame": "CY2022Q4I",
    },
]


def _cve_facts() -> dict:
    return {
        "us-gaap": {},
        "dei": {},
        "ifrs-full": {
            "CurrentAssets": _concept(_CVE_PRIMARY_CURRENT_ASSETS),
            "CurrentAssetsOtherThanAssetsOrDisposalGroupsClassifiedAsHeldForSaleOrAsHeldForDistributionToOwners": (
                _concept(_CVE_FALLBACK_CURRENT_ASSETS_EXCL_HFS)
            ),
        },
    }


class TestCrossConceptFallbackDoesNotOverridePrimary:
    def test_primary_concept_value_wins_over_frame_tagged_fallback(self) -> None:
        client = _FakeClient(_cve_facts())
        rows = get_balance_sheet(client, "CVE", "annual")
        fy2022 = next(r for r in rows if r.get("fiscal_year") == 2022)
        assert fy2022["assets_current"] == 12_430_000_000

    def test_fallback_still_fills_a_genuinely_empty_column(self) -> None:
        facts = _cve_facts()
        del facts["ifrs-full"]["CurrentAssets"]
        client = _FakeClient(facts)
        rows = get_balance_sheet(client, "CVE", "annual")
        fy2022 = next(r for r in rows if r.get("fiscal_year") == 2022)
        assert fy2022["assets_current"] == 0
