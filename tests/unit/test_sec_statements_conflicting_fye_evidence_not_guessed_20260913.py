"""Regression test for a fiscal-year-end misdetection bug in
_aggregate_concepts_build_unit_context (utils/external/sec_statements_unit_context.py):

A filer that genuinely changed its fiscal year end mid-history (ABVC/ABVC BioPharma: real
FYE September 30 through FY2015, changed to December 31 from FY2018 onward) has MULTIPLE
real, direct FY-duration-fact end months on file for the same concept. Before this fix, that
ambiguity (neither unanimous December nor unanimous non-December) fell through to an
unreliable quarterly self-consistency guess - live-confirmed via ABVC: the guess was
independently, coincidentally satisfied by a genuine quarterly fact, flipping
has_december_fiscal_year_end to True and wrongly rejecting ABVC's own real September-ending
"Revenues" facts via the AMZN-rolling-window guard (a non-December-fiscal-year filer's annual
total must end in December, or it's rejected as a rolling window), leaving "revenue" NULL for
a fiscal year that has a real, correct, already-known value ($3,360 for FY2015).

Fix: explicit conflicting direct evidence (more than one distinct FY-duration-fact end month
on file) must never be second-guessed by the indirect quarterly guess either - same principle
as the unanimous-agreement case (see test_sec_statements_non_december_fye_quarterly_month_
coincidence_20260913.py, the UHAL fix), just the opposite conclusion: we know for certain
there is no single stable answer, instead of inferring one from a single fact.
"""

from utils.external.sec_statements import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0001173313"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


class TestConflictingFyeEvidenceNotGuessed:
    def test_abvc_september_fye_revenue_not_rejected_by_coincidental_quarterly_match(self):
        facts = {
            "us-gaap": {
                "Revenues": _concept(
                    [
                        # Real September-ending fiscal years (ABVC's original FYE).
                        {
                            "start": "2013-10-01",
                            "end": "2014-09-18",
                            "val": 0,
                            "filed": "2015-11-27",
                            "fp": "FY",
                            "fy": 2015,
                            "form": "10-K",
                        },
                        {
                            "start": "2014-10-01",
                            "end": "2015-09-30",
                            "val": 3360,
                            "filed": "2015-11-27",
                            "fp": "FY",
                            "fy": 2015,
                            "form": "10-K",
                        },
                        # Real December-ending fiscal years (ABVC's later, changed FYE).
                        {
                            "start": "2018-01-01",
                            "end": "2018-12-31",
                            "val": 1000000,
                            "filed": "2019-05-15",
                            "fp": "FY",
                            "fy": 2019,
                            "form": "10-K",
                        },
                        # A genuine, promptly-filed quarterly fact whose end month (09)
                        # coincidentally satisfies the December-fiscal-year quarterly
                        # self-consistency guess's Q3->09 mapping.
                        {
                            "start": "2020-07-01",
                            "end": "2020-09-30",
                            "val": 500000,
                            "filed": "2020-11-13",
                            "fp": "Q3",
                            "fy": 2020,
                            "form": "10-Q",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "ABVC", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2015]["revenues"] == 3360
