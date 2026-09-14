"""Regression test for a systemic non-December-fiscal-year-end quarterly mislabeling bug in
_aggregate_concepts_resolve_entry_period (utils/external/sec_statements_entry_resolution.py) -
goal session 2026-09-13/14, quarantine-backlog audit, ARWR/NB live-confirmed via real SEC
companyfacts JSON.

`period_year` for a duration fact was always derived as the CALENDAR YEAR of the fact's own end
date, with no correction for a non-December fiscal-year-end filer. For any such filer, the
quarter immediately after the fiscal year starts (e.g. Oct-Dec for a September FYE) ends in a
calendar year that is ONE LESS than the real fiscal year it belongs to -
annual_income_statement labels a fiscal year by the calendar year it ENDS in (ARWR's real
FY2017 = Oct2016-Sep2017, labeled 2017), so this quarter silently collided with the PRIOR real
fiscal year's own quarters in `quarterly_income_statement` instead.

Live-confirmed via ARWR (real FYE September 30, CIK 0000879407): real FY2017 Q1 (period
2016-10-01/2016-12-31, $4,365,496) was stored as fiscal_year=2016/Q1 - not a shell-company
comparative-restatement ambiguity (ARWR is a real, continuously-operating biotech), a pure
labeling bug. Silent for most non-December-FYE filers (a swapped Q1 between two similarly-sized
adjacent fiscal years doesn't trip any magnitude check) - only visible here because ARWR's
dramatic YoY growth ($158K FY2016 -> $31.4M FY2017) made the mislabeled quarter's mismatch large
enough to flag `quarterly_revenue_sum_vs_annual_extreme`.

Fixture below is a minimal but structurally faithful excerpt of ARWR's real companyfacts JSON:
unanimous FY-tagged facts unambiguously establishing FYE month 9, plus the real Q1/Q2/Q3 facts
for FY2016 and FY2017 whose calendar-end-year would otherwise misassign FY2017 Q1.
"""

from utils.external.sec_income_statement import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000879407"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


# Real ARWR (Arrowhead Pharmaceuticals) Revenues facts, September 30 FYE.
_ARWR_REVENUES_ENTRIES = [
    # Unanimous FY-tagged annual facts (all real full-year spans, ~365/366 days) - establishes
    # fye_month=9 unambiguously.
    {
        "start": "2010-10-01",
        "end": "2011-09-30",
        "val": 296139,
        "fp": "FY",
        "form": "10-K",
        "fy": 2011,
        "filed": "2011-12-01",
    },
    {
        "start": "2011-10-01",
        "end": "2012-09-30",
        "val": 146875,
        "fp": "FY",
        "form": "10-K",
        "fy": 2012,
        "filed": "2012-12-01",
    },
    {
        "start": "2014-10-01",
        "end": "2015-09-30",
        "val": 382000,
        "fp": "FY",
        "form": "10-K",
        "fy": 2015,
        "filed": "2015-12-01",
    },
    {
        "start": "2015-10-01",
        "end": "2016-09-30",
        "val": 158333,
        "fp": "FY",
        "form": "10-K",
        "fy": 2016,
        "filed": "2016-12-01",
    },
    {
        "start": "2016-10-01",
        "end": "2017-09-30",
        "val": 31407709,
        "fp": "FY",
        "form": "10-K",
        "fy": 2017,
        "filed": "2017-12-01",
    },
    # SEC's own fp tagging is unreliable for short comparative facts within a filing - some
    # quarterly-length facts get mistagged fp="FY" too (same issue documented in
    # sec_statements_entry_resolution.py's "Use period end year..." comment for the `fy`
    # field). These must NOT count as genuine FY evidence (span filter in
    # _aggregate_concepts_build_unit_context excludes them) or fye_month would spuriously
    # resolve to conflicting-evidence/None instead of the real unanimous 9.
    {
        "start": "2012-10-01",
        "end": "2012-12-31",
        "val": 159016,
        "fp": "FY",
        "form": "10-K",
        "fy": 2014,
        "filed": "2014-02-01",
    },
    {
        "start": "2013-01-01",
        "end": "2013-03-31",
        "val": 43750,
        "fp": "FY",
        "form": "10-K",
        "fy": 2014,
        "filed": "2014-02-01",
    },
    # Real FY2016 (Oct2015-Sep2016) discrete quarters.
    {
        "start": "2015-10-01",
        "end": "2015-12-31",
        "val": 43750,
        "fp": "Q1",
        "form": "10-Q",
        "fy": 2016,
        "filed": "2016-02-01",
    },
    {
        "start": "2016-01-01",
        "end": "2016-03-31",
        "val": 43750,
        "fp": "Q2",
        "form": "10-Q",
        "fy": 2016,
        "filed": "2016-05-01",
    },
    {
        "start": "2016-04-01",
        "end": "2016-06-30",
        "val": 39583,
        "fp": "Q3",
        "form": "10-Q",
        "fy": 2016,
        "filed": "2016-08-01",
    },
    # Real FY2017 (Oct2016-Sep2017) Q1 - the mislabeling case: end date falls in calendar 2016,
    # but this is FY2017's own Q1, not FY2016's Q4/anything.
    {
        "start": "2016-10-01",
        "end": "2016-12-31",
        "val": 4365496,
        "fp": "Q1",
        "form": "10-Q",
        "fy": 2017,
        "filed": "2017-02-01",
    },
    {
        "start": "2017-01-01",
        "end": "2017-03-31",
        "val": 8985930,
        "fp": "Q2",
        "form": "10-Q",
        "fy": 2017,
        "filed": "2017-05-01",
    },
    {
        "start": "2017-04-01",
        "end": "2017-06-30",
        "val": 9342498,
        "fp": "Q3",
        "form": "10-Q",
        "fy": 2017,
        "filed": "2017-08-01",
    },
]


class TestNonDecemberFyeQuarterlyYearOffset:
    def test_arwr_fy2017_q1_not_collapsed_into_fy2016(self):
        facts = {"us-gaap": {"Revenues": _concept(_ARWR_REVENUES_ENTRIES)}}
        client = _FakeClient(facts)

        rows = get_income_statement(client, "ARWR", period="quarterly")
        by_key = {(r["fiscal_year"], r["fiscal_period"]): r for r in rows}

        assert (2016, "Q1") in by_key
        assert (2017, "Q1") in by_key
        # The real FY2016 Q1 (Oct-Dec 2015, $43,750) must stay in fiscal_year=2016, not be
        # overwritten or collided with FY2017's Q1.
        assert by_key[(2016, "Q1")]["revenues"] == 43750
        # The real FY2017 Q1 (Oct-Dec 2016, $4,365,496) must land in fiscal_year=2017, not
        # fiscal_year=2016 (the bug this test guards against).
        assert by_key[(2017, "Q1")]["revenues"] == 4365496

    def test_arwr_fy2016_quarters_sum_close_to_annual(self):
        facts = {"us-gaap": {"Revenues": _concept(_ARWR_REVENUES_ENTRIES)}}
        client = _FakeClient(facts)

        quarterly = {
            (r["fiscal_year"], r["fiscal_period"]): r for r in get_income_statement(client, "ARWR", period="quarterly")
        }
        annual = {r["fiscal_year"]: r for r in get_income_statement(client, "ARWR", period="annual")}

        fy2016_q1q2q3_sum = (
            quarterly[(2016, "Q1")]["revenues"]
            + quarterly[(2016, "Q2")]["revenues"]
            + quarterly[(2016, "Q3")]["revenues"]
        )
        # Real Q4 (not in this fixture) is $31,250, so the full sum equals the annual total
        # exactly - the partial Q1-Q3 sum here must stay comfortably under the annual total,
        # not wildly overshoot it as it did with FY2017's Q1 wrongly mixed in (127,083 vs
        # bug-corrupted ~4.4M+127,083).
        assert fy2016_q1q2q3_sum < annual[2016]["revenues"]
        assert fy2016_q1q2q3_sum == 43750 + 43750 + 39583
