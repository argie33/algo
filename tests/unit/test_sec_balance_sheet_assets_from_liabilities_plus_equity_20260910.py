"""Regression test for the "Missing SEC/XBRL data" under-500 push, BTTC/XLAB live-confirmed
2026-09-10.

Both filers tag "Liabilities" and "StockholdersEquity" every period but have never tagged
"Assets" (or any combined "LiabilitiesAndStockholdersEquity" total) anywhere in their full
companyfacts history - live-confirmed via real SEC companyfacts JSON: every us-gaap key
present for each filer, none asset-shaped. roa/asset_turnover/gross_profitability were
falling to "no_recent_total_assets_reported" (implies a fixable extraction gap) when the real
answer is directly derivable from the balance-sheet identity: Assets = Liabilities +
StockholdersEquity.

Fix: `_fill_assets_from_liabilities_plus_equity` in sec_balance_sheet.py sums the two
directly-tagged halves whenever `assets` is still None after every earlier concept/derivation
and both halves are real (non-None) values.
"""

from utils.external.sec_balance_sheet import get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0002000000"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


class TestAssetsFromLiabilitiesPlusEquity:
    def test_bttc_shaped_filer_never_tagging_assets_gets_derived_total(self) -> None:
        facts = {
            "us-gaap": {
                "Liabilities": _concept(
                    [
                        {
                            "end": "2025-12-31",
                            "val": 167_120,
                            "filed": "2026-03-01",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                            "accn": "A",
                        },
                    ]
                ),
                "StockholdersEquity": _concept(
                    [
                        {
                            "end": "2025-12-31",
                            "val": -167_120,
                            "filed": "2026-03-01",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                            "accn": "A",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "BTTC", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["liabilities"] == 167_120
        assert by_year[2025]["stockholders_equity"] == -167_120
        assert by_year[2025]["assets"] == 0

    def test_never_overwrites_a_real_directly_tagged_assets_value(self) -> None:
        facts = {
            "us-gaap": {
                "Assets": _concept(
                    [
                        {
                            "end": "2025-12-31",
                            "val": 500_000,
                            "filed": "2026-03-01",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                            "accn": "A",
                        },
                    ]
                ),
                "Liabilities": _concept(
                    [
                        {
                            "end": "2025-12-31",
                            "val": 100_000,
                            "filed": "2026-03-01",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                            "accn": "A",
                        },
                    ]
                ),
                "StockholdersEquity": _concept(
                    [
                        {
                            "end": "2025-12-31",
                            "val": 400_000,
                            "filed": "2026-03-01",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                            "accn": "A",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "REAL", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        # Directly-tagged Assets wins even though it doesn't equal liabilities+equity here
        # (real filers can have rounding/timing mismatches) - derivation is fallback-only.
        assert by_year[2025]["assets"] == 500_000

    def test_only_one_half_present_leaves_assets_none(self) -> None:
        facts = {
            "us-gaap": {
                "Liabilities": _concept(
                    [
                        {
                            "end": "2025-12-31",
                            "val": 100_000,
                            "filed": "2026-03-01",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                            "accn": "A",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "PARTIAL", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025].get("assets") is None
