"""Regression test for a genuine filer-side XBRL tagging error, live-confirmed via BTCS
(CIK 1436229) real SEC companyfacts JSON: its 2012 Q1/Q2/Q3 10-Qs (and 2014 10-Q/A
amendments) each independently mistagged the SAME full FY2010 annual total (start=2010-01-01,
end=2010-12-31, 365 days) as that quarter's own "prior year" comparative figure - fp="Q1" in
the Q1 10-Q, fp="Q2" in the Q2 10-Q, fp="Q3" in the Q3 10-Q. Unlike the OFRM/DXC comparative-
fp-aliasing bug class (`b8c37c0bc`, one fact mistagged into a DIFFERENT quarter's bucket), this
fact's own fp tag already equals a real Q1-Q4 value, so it skips the derived_fp relocation
logic entirely and was accepted at face value with no duration-span check at all - with no
genuine discrete quarterly fact ever filed for FY2010 to tiebreak against, each mistagged
annual total became the sole occupant of its bucket.

Fix: quarterly extraction now mirrors the annual branch's own existing span_days<330 guard
("Real single-quarter/partial-year data - not annual") - a fact whose own fp already equals
Q1-Q4 is rejected from the quarterly bucket entirely when its span is >=330 days (annual-
shaped), the same threshold used everywhere else in this file to identify an annual-length
duration.
"""

from utils.external.sec_statements import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0001436229"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


class TestAnnualFactMistaggedAsQuarterlyFp:
    def test_annual_shaped_fact_tagged_q1_q2_q3_excluded_from_quarterly_buckets(self):
        """BTCS-shaped fixture: three separate filings each mistag the SAME full-year total
        as a different quarter's own comparative. None of the three quarterly buckets has a
        genuine competing fact - the mistagged annual total must not populate any of them."""
        facts = {
            "us-gaap": {
                "ProfitLoss": _concept(
                    [
                        # 2012 Q1 10-Q's own "prior year" comparative - actually the full
                        # FY2010 annual total, mistagged fp="Q1".
                        {
                            "start": "2010-01-01",
                            "end": "2010-12-31",
                            "val": 105115,
                            "filed": "2012-05-10",
                            "fp": "Q1",
                            "fy": 2012,
                            "form": "10-Q",
                            "accn": "0001213900-12-002379",
                        },
                        # 2012 Q2 10-Q's own "prior year" comparative - same mistake, fp="Q2".
                        {
                            "start": "2010-01-01",
                            "end": "2010-12-31",
                            "val": 165178,
                            "filed": "2012-08-02",
                            "fp": "Q2",
                            "fy": 2012,
                            "form": "10-Q",
                            "accn": "0001213900-12-004133",
                        },
                        # 2012 Q3 10-Q's own "prior year" comparative - same mistake, fp="Q3".
                        {
                            "start": "2010-01-01",
                            "end": "2010-12-31",
                            "val": 105115,
                            "filed": "2012-11-09",
                            "fp": "Q3",
                            "fy": 2012,
                            "form": "10-Q",
                            "accn": "0001213900-12-005995",
                        },
                        # The one genuine quarterly-shaped fact on file for 2010: a real H1
                        # cumulative, correctly tagged fp="Q2" by the filer at the time.
                        {
                            "start": "2010-01-01",
                            "end": "2010-06-30",
                            "val": 271788,
                            "filed": "2011-08-22",
                            "fp": "Q2",
                            "fy": 2011,
                            "form": "10-Q",
                            "accn": "0001213900-11-004630",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "BTCS", period="quarterly")
        by_year_quarter = {(r["fiscal_year"], r["fiscal_period"]): r for r in rows}

        # Q1: no genuine fact ever existed - the mistagged annual total must not appear.
        assert (2010, "Q1") not in by_year_quarter or "profit_loss" not in by_year_quarter[(2010, "Q1")]
        # Q2: the genuine H1 cumulative (271788) must win, not the mistagged annual (165178).
        assert by_year_quarter[(2010, "Q2")]["profit_loss"] == 271788
        # Q3: no genuine fact ever existed - the mistagged annual total must not appear.
        assert (2010, "Q3") not in by_year_quarter or "profit_loss" not in by_year_quarter[(2010, "Q3")]

    def test_annual_branch_unaffected_by_quarterly_only_guard(self):
        """The new guard is scoped to period=='quarterly' only - the exact same annual-shaped
        fact must still populate the annual bucket normally."""
        facts = {
            "us-gaap": {
                "ProfitLoss": _concept(
                    [
                        {
                            "start": "2010-01-01",
                            "end": "2010-12-31",
                            "val": 105115,
                            "filed": "2014-01-28",
                            "fp": "FY",
                            "fy": 2011,
                            "form": "10-K/A",
                            "accn": "0001213900-14-000508",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "BTCS", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2010]["profit_loss"] == 105115

    def test_genuine_nine_month_cumulative_quarterly_fact_still_accepted(self):
        """Guard against over-fixing: a real 9-month (~270 day) YTD cumulative fact, well
        short of the 330-day annual threshold, must still populate its Q3 bucket normally."""
        facts = {
            "us-gaap": {
                "ProfitLoss": _concept(
                    [
                        {
                            "start": "2024-01-01",
                            "end": "2024-09-30",
                            "val": 500_000,
                            "filed": "2024-11-01",
                            "fp": "Q3",
                            "fy": 2024,
                            "form": "10-Q",
                            "accn": "0000000000-24-000003",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "GENUINE9MO", period="quarterly")
        by_year_quarter = {(r["fiscal_year"], r["fiscal_period"]): r for r in rows}

        assert by_year_quarter[(2024, "Q3")]["profit_loss"] == 500_000
