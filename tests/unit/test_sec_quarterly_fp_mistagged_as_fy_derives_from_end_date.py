"""Regression test for a quarterly-extraction bug found live 2026-08-22 (goal session:
real-money-readiness audit, following up on the quarterly_balance_sheet residual-
contamination investigation).

AGNC (AGNC Investment Corp, a large mortgage REIT) live-confirmed via real companyfacts
JSON: every one of its FY2020 10-Q filings tags fp="FY" instead of "Q1"/"Q2"/"Q3" (a
filer-side XBRL tagging quirk isolated to that fiscal year - its FY2021 10-Qs correctly
tag fp="Q1" etc). get_balance_sheet()'s quarterly extraction gates strictly on
`fp in ("Q1","Q2","Q3","Q4")`, so the entire fiscal year silently dropped out of
quarterly extraction - not a wrong value, zero rows at all for that year - even though
real, distinct, correctly-deduped quarter-end instant values exist (Q1=$85.137B,
Q2=$89.853B, Q3=$79.968B). quarterly_balance_sheet was left showing 3 straight quarters
frozen at the FY-end value ($81.817B) from a stale pre-fix write that nothing since has
touched, because the current extraction logic produces zero new rows to overwrite it
with.

Fixed by deriving a fallback quarter from the entry's own end-date month, but ONLY for
instant facts (no "start" - the existing accn+max-end-date dedup already guarantees
these are each filing's own genuine current-period value, not a comparative echo) from a
filer whose real fiscal year end (established from its own annual-report-form instant
facts) is genuinely December - deliberately not applied to non-December fiscal years,
where a bare calendar-month-to-quarter mapping would be wrong.
"""

from utils.external.sec_statements import get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0001423689"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


class TestQuarterlyFpMistaggedAsFyDerivesFromEndDate:
    def test_fy2020_style_fp_mistagged_10qs_still_produce_distinct_quarters(self) -> None:
        # Real AGNC-shaped data: three FY2020 10-Qs all mistag fp="FY", plus the real
        # FY2020 10-K (also fp="FY", as expected for a 10-K) establishing a December
        # fiscal year end, plus a correctly-tagged FY2021 Q1 10-Q for contrast.
        facts = {
            "us-gaap": {
                "Assets": _concept(
                    [
                        {
                            "end": "2020-03-31",
                            "val": 85_137_000_000,
                            "filed": "2020-05-11",
                            "fp": "FY",
                            "fy": 2020,
                            "form": "10-Q",
                            "accn": "a1",
                        },
                        {
                            "end": "2020-06-30",
                            "val": 89_853_000_000,
                            "filed": "2020-08-07",
                            "fp": "FY",
                            "fy": 2020,
                            "form": "10-Q",
                            "accn": "a2",
                        },
                        {
                            "end": "2020-09-30",
                            "val": 79_968_000_000,
                            "filed": "2020-11-05",
                            "fp": "FY",
                            "fy": 2020,
                            "form": "10-Q",
                            "accn": "a3",
                        },
                        {
                            "end": "2020-12-31",
                            "val": 81_817_000_000,
                            "filed": "2021-02-26",
                            "fp": "FY",
                            "fy": 2020,
                            "form": "10-K",
                            "accn": "a4",
                        },
                        {
                            "end": "2021-03-31",
                            "val": 85_545_000_000,
                            "filed": "2021-05-07",
                            "fp": "Q1",
                            "fy": 2021,
                            "form": "10-Q",
                            "accn": "a5",
                        },
                    ]
                )
            }
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "AGNC", period="quarterly")

        by_year_period = {(r["fiscal_year"], r["fiscal_period"]): r.get("assets") for r in rows}
        assert by_year_period[(2020, "Q1")] == 85_137_000_000
        assert by_year_period[(2020, "Q2")] == 89_853_000_000
        assert by_year_period[(2020, "Q3")] == 79_968_000_000
        assert by_year_period[(2021, "Q1")] == 85_545_000_000

    def test_non_december_fiscal_year_end_does_not_get_calendar_quarter_guess(self) -> None:
        # A non-calendar fiscal year filer (FYE September, like AAPL) whose 10-Qs also
        # happen to mistag fp="FY" must NOT get a calendar-month-based quarter guess -
        # this fix is deliberately scoped to December fiscal year ends only.
        facts = {
            "us-gaap": {
                "Assets": _concept(
                    [
                        {
                            "end": "2020-03-31",
                            "val": 1_000_000,
                            "filed": "2020-05-11",
                            "fp": "FY",
                            "fy": 2020,
                            "form": "10-Q",
                            "accn": "b1",
                        },
                        {
                            "end": "2020-09-30",
                            "val": 2_000_000,
                            "filed": "2020-11-05",
                            "fp": "FY",
                            "fy": 2020,
                            "form": "10-K",
                            "accn": "b2",
                        },
                    ]
                )
            }
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "NONCAL", period="quarterly")

        by_year_period = {(r["fiscal_year"], r["fiscal_period"]): r.get("assets") for r in rows}
        assert (2020, "Q1") not in by_year_period

    def test_correctly_tagged_quarters_are_unaffected(self) -> None:
        facts = {
            "us-gaap": {
                "Assets": _concept(
                    [
                        {
                            "end": "2021-03-31",
                            "val": 85_545_000_000,
                            "filed": "2021-05-07",
                            "fp": "Q1",
                            "fy": 2021,
                            "form": "10-Q",
                            "accn": "c1",
                        },
                        {
                            "end": "2021-12-31",
                            "val": 88_000_000_000,
                            "filed": "2022-02-23",
                            "fp": "FY",
                            "fy": 2021,
                            "form": "10-K",
                            "accn": "c2",
                        },
                    ]
                )
            }
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "AGNC", period="quarterly")

        by_year_period = {(r["fiscal_year"], r["fiscal_period"]): r.get("assets") for r in rows}
        assert by_year_period[(2021, "Q1")] == 85_545_000_000
