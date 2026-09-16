"""Regression test for an annual-row period_end mis-anchoring bug in
_aggregate_concepts() (utils/external/sec_statements_aggregate.py):

Live-verified 2026-09-16 via CHKP (Check Point Software, a 20-F foreign private issuer):
annual_balance_sheet FY2025 held total_assets=$5,699,600,000 and stockholders_equity=
$32,700,000, but SEC's real FY2025 20-F (period end 2025-12-31) reports total_assets=
$7,806,400,000 and stockholders_equity=$2,882,100,000 - confirmed via both XBRL US and SEC's
own companyfacts JSON. The bad $5.6996B/$32.7M figures are CHKP's own real Q3 2025 (end
2025-09-30) facts, filed earlier via a 6-K (filed 2025-12-02), re-tagged 2026-03-31 alongside
in-scope comparatives that the FY2025 20-F itself (filed 2026-03-31) also carries.

Root cause: the annual row's `period_end` bookkeeping field is set ONCE, by whichever entry
first creates the (fiscal_year, "FY") key via `rows.setdefault(...)` - and every later instant
fact whose own end date disagrees with that anchor is unconditionally skipped (`continue`),
regardless of its own form authority. "Assets" is the first concept processed for every
filer (sec_balance_sheet.py's concepts list), so whichever of its own entries for fy=2025
appears first in SEC's companyfacts array (the earlier-filed 6-K's Q3 snapshot, not the
later-filed 20-F's real year-end fact) permanently anchors period_end for the ENTIRE row -
silently rejecting every subsequent concept's real FY-end fact (including "Assets" own later
20-F entry) for the rest of that fiscal year.

Fix: a genuine annual-report-form entry (10-K/20-F/40-F) may correct an already-set period_end
anchor once, if that anchor wasn't itself set by an annual-report-form entry - "structural form
authority beats filing/iteration order", the same principle already applied elsewhere in this
file's form-rank tiebreaks.
"""

from utils.external.sec_statements import get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0001015922"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


class TestFpiInterimPeriodEndAnchor:
    def test_interim_6k_snapshot_does_not_permanently_anchor_the_annual_row(self):
        # Real CHKP-shaped data: the Q3 2025 6-K's own "Assets" fact (filed earlier, form
        # 6-K) appears BEFORE the true FY2025 20-F fact in SEC's companyfacts array order -
        # exactly the ordering that triggered the live bug.
        facts = {
            "us-gaap": {
                "Assets": _concept(
                    [
                        {
                            "end": "2025-09-30",
                            "val": 5_699_600_000,
                            "filed": "2025-12-02",
                            "fp": "Q3",
                            "fy": 2025,
                            "form": "6-K",
                        },
                        {
                            "end": "2025-12-31",
                            "val": 7_806_400_000,
                            "filed": "2026-03-31",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "20-F",
                        },
                    ]
                ),
                "StockholdersEquity": _concept(
                    [
                        {
                            "end": "2025-09-30",
                            "val": 3_079_800_000,
                            "filed": "2025-12-02",
                            "fp": "Q3",
                            "fy": 2025,
                            "form": "6-K",
                        },
                        {
                            "end": "2025-12-31",
                            "val": 2_882_100_000,
                            "filed": "2026-03-31",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "20-F",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "CHKP", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["assets"] == 7_806_400_000
        assert by_year[2025]["stockholders_equity"] == 2_882_100_000

    def test_non_annual_form_still_cannot_override_an_already_correct_annual_anchor(self):
        """The fix must not let a LATER, non-annual-report-form entry re-anchor a row whose
        period_end was already correctly established by a real annual-report-form entry -
        that's the original LOVE-case protection this guard exists for, and must survive."""
        facts = {
            "us-gaap": {
                "Assets": _concept(
                    [
                        {
                            "end": "2025-12-31",
                            "val": 7_806_400_000,
                            "filed": "2026-03-31",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "20-F",
                        },
                        # A later-filed, unrelated interim snapshot for the same calendar
                        # year - must be rejected, not allowed to reopen the anchor.
                        {
                            "end": "2025-06-30",
                            "val": 999_000_000,
                            "filed": "2026-04-01",
                            "fp": "Q2",
                            "fy": 2025,
                            "form": "6-K",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "CHKP", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["assets"] == 7_806_400_000
