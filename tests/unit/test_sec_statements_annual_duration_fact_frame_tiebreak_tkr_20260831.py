"""Regression test for a fiscal-year revenue mis-selection bug in _aggregate_concepts()
(utils/external/sec_statements.py):

Live-verified 2026-08-31 via TKR (Timken Company, CIK 0000098362) real SEC companyfacts JSON:
annual_income_statement.revenue for fiscal_year=2015 stored $20,600,000, but the real total
(SalesRevenueGoodsNet, TKR's own FY2015 10-K) is $2,872,300,000 - understated ~139x.

Both values are genuine annual-length (>=330-day) duration facts (real data, not malformed) that
FIRST appear together in the SAME filing (accn 0000098362-16-000097, filed 2016-02-24):
  - real:      start=2015-01-01, end=2015-12-31, val=$2,872,300,000
  - spurious:  start=2014-10-01, end=2015-09-30, val=$20,600,000 (~0.7% of real revenue - a
               stray off-calendar sub-line or filing-agent tagging error, not TKR's real total)
Both then get re-cited VERBATIM in 2 subsequent years' 10-Ks (accn ...17-000031 filed
2017-02-21, accn ...18-000033 filed 2018-02-15) with matching filed dates each time - so the
old plain "latest filed wins" tiebreak (strict >) never distinguished them; whichever was
iterated first in SEC's JSON response silently won.

The one reliable difference across all 3 occurrences: the real value eventually carries
frame="CY2015" (SEC's own signal for "the single canonical value for this standardized
period" - the identical signal already trusted for the PMT instant-fact case, see
test_sec_statements_instant_fact_prefers_latest_end_date.py's frame test), the spurious value
never does. Fixed by applying that same frame-preference principle to the annual
duration-vs-duration tiebreak too, before falling back to plain filed-date comparison.
"""

from utils.external.sec_statements import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000098362"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


class TestAnnualDurationFactFrameTiebreak:
    def test_tkr_real_annual_revenue_wins_over_off_calendar_spurious_value(self):
        # Real TKR-shaped data: both facts first appear in the same accn/filed date, then
        # get re-cited identically in 2 later filings - the real value gains a frame tag
        # in its later citations, the spurious one never does. Spurious value listed
        # AFTER the real one in list order (matches the ordering that produced the live
        # bug, per the "whichever iterates first wins" failure mode).
        facts = {
            "us-gaap": {
                "SalesRevenueGoodsNet": _concept(
                    [
                        {
                            "start": "2015-01-01",
                            "end": "2015-12-31",
                            "val": 2_872_300_000,
                            "accn": "0000098362-16-000097",
                            "fy": 2015,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2016-02-24",
                        },
                        {
                            "start": "2014-10-01",
                            "end": "2015-09-30",
                            "val": 20_600_000,
                            "accn": "0000098362-16-000097",
                            "fy": 2015,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2016-02-24",
                        },
                        {
                            "start": "2015-01-01",
                            "end": "2015-12-31",
                            "val": 2_872_300_000,
                            "accn": "0000098362-17-000031",
                            "fy": 2016,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2017-02-21",
                        },
                        {
                            "start": "2014-10-01",
                            "end": "2015-09-30",
                            "val": 20_600_000,
                            "accn": "0000098362-17-000031",
                            "fy": 2016,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2017-02-21",
                        },
                        {
                            "start": "2015-01-01",
                            "end": "2015-12-31",
                            "val": 2_872_300_000,
                            "accn": "0000098362-18-000033",
                            "fy": 2017,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2018-02-15",
                            "frame": "CY2015",
                        },
                        {
                            "start": "2014-10-01",
                            "end": "2015-09-30",
                            "val": 20_600_000,
                            "accn": "0000098362-18-000033",
                            "fy": 2017,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2018-02-15",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "TKR", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2015]["sales_revenue_goods_net"] == 2_872_300_000, (
            f"Expected TKR's real FY2015 revenue $2,872,300,000, got "
            f"{by_year[2015].get('sales_revenue_goods_net')!r} - a value of $20,600,000 means "
            f"the frame-tiebreak regression is back"
        )

    def test_spurious_value_first_in_list_order_still_loses(self):
        """The fix must not depend on iteration order - the spurious value listed FIRST
        must still lose once the frame-tagged real value is processed."""
        facts = {
            "us-gaap": {
                "SalesRevenueGoodsNet": _concept(
                    [
                        {
                            "start": "2014-10-01",
                            "end": "2015-09-30",
                            "val": 20_600_000,
                            "accn": "0000098362-18-000033",
                            "fy": 2017,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2018-02-15",
                        },
                        {
                            "start": "2015-01-01",
                            "end": "2015-12-31",
                            "val": 2_872_300_000,
                            "accn": "0000098362-18-000033",
                            "fy": 2017,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2018-02-15",
                            "frame": "CY2015",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "TKR", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2015]["sales_revenue_goods_net"] == 2_872_300_000

    def test_neither_frame_tagged_falls_back_to_filed_date_as_before(self):
        """Sanity check: when NEITHER candidate has a frame tag, the fix must not change
        anything - falls back to the pre-existing plain filed-date tiebreak."""
        facts = {
            "us-gaap": {
                "Revenues": _concept(
                    [
                        {
                            "start": "2020-01-01",
                            "end": "2020-12-31",
                            "val": 100_000_000,
                            "fy": 2020,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2021-02-01",
                        },
                        {
                            "start": "2020-01-01",
                            "end": "2020-12-31",
                            "val": 105_000_000,  # restated, filed later, no frame either
                            "fy": 2020,
                            "fp": "FY",
                            "form": "10-K/A",
                            "filed": "2021-06-01",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "TEST", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2020]["revenues"] == 105_000_000
