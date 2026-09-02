"""Regression test restoring `fd1c8a99f`'s fix (originally landed 2026-09-01, but only ever
merged onto the unmerged `growth-factor-realignment` branch, not `main`), plus a new guard
for a false-positive it would otherwise reintroduce.

Live-confirmed via OFRM (Once Upon a Farm, PBC, CIK 1696556) real companyfacts JSON: its
Q2-2026 10-Q (accn 0001696556-26-000025) correctly tags its own discrete Q2 NetIncomeLoss
(start=2026-04-01/end=2026-06-30, val=-$4,950,000, frame="CY2026Q2") but ALSO re-tags its
Q1-2026 comparative (start=2026-01-01/end=2026-03-31, val=-$15,811,000, frame="CY2026Q1")
with fp="Q2" - the FILING's own reporting period, not the comparative fact's real period.
Both facts span a genuine single quarter (89/90 days), so the existing discrete-vs-cumulative
shorter-span-wins tiebreak (2026-08-29, the META fix) isn't a meaningful signal between them -
Jan-Mar's 89 days is coincidentally shorter than Apr-Jun's 90 (February is short), so the
mistagged comparative silently won by pure calendar-month coincidence, not correctness.

Live-confirmed regression via `git log -S`/`git merge-base --is-ancestor`: `fd1c8a99f` only
ever exists on the unmerged `growth-factor-realignment` branch. `main` picked up neither half
(the `has_december_fiscal_year_end` self-consistency fallback, nor the "not start_date" removal
+ span gate on the derived-fp override) - confirmed live by re-running
`get_income_statement(client, 'OFRM', period='quarterly')` against real SEC data and finding
the exact original bug reproduced.

Restoring the fix verbatim would also reintroduce a NEW false positive, live-confirmed via DXC
(Deloitte/DXC Technology, a March-fiscal-year-end filer, CIK 1688568): its cash-flow concepts'
self-consistency check finds "matches" that are actually ~183/364-day CUMULATIVE comparative
facts landing on a calendar-quarter-end month by coincidence, not genuine December-FYE
evidence - without narrowing the self-consistency check to a genuine single-quarter span
(80-100 days, the same gate already used for the override itself), DXC's real ~90-day Q1
fact would get wrongly relabeled Q2 and clobber its real (183-day) Q2 cumulative fact.
"""

from utils.external.sec_statements import get_cash_flow, get_income_statement


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000000000"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


class TestQuarterlyDurationFactComparativeFpAliasing:
    def test_q1_comparative_mistagged_as_q2_does_not_clobber_real_q2(self):
        facts = {
            "us-gaap": {
                "NetIncomeLoss": _concept(
                    [
                        # OFRM's own Q1-2026 10-Q: the real, correctly-tagged Q1 value.
                        {
                            "start": "2026-01-01",
                            "end": "2026-03-31",
                            "val": -15_811_000,
                            "filed": "2026-05-07",
                            "fp": "Q1",
                            "fy": 2026,
                            "form": "10-Q",
                            "accn": "0001696556-26-000015",
                        },
                        # The bug: same value, re-tagged fp="Q2" as the Q2 filing's own
                        # Q1 comparative (frame confirms it's genuinely the Q1 period).
                        {
                            "start": "2026-01-01",
                            "end": "2026-03-31",
                            "val": -15_811_000,
                            "filed": "2026-08-06",
                            "fp": "Q2",
                            "fy": 2026,
                            "form": "10-Q",
                            "accn": "0001696556-26-000025",
                            "frame": "CY2026Q1",
                        },
                        # H1 cumulative, also carrying fp="Q2" (the filing's own period).
                        {
                            "start": "2026-01-01",
                            "end": "2026-06-30",
                            "val": -20_761_000,
                            "filed": "2026-08-06",
                            "fp": "Q2",
                            "fy": 2026,
                            "form": "10-Q",
                            "accn": "0001696556-26-000025",
                        },
                        # The real discrete Q2 value.
                        {
                            "start": "2026-04-01",
                            "end": "2026-06-30",
                            "val": -4_950_000,
                            "filed": "2026-08-06",
                            "fp": "Q2",
                            "fy": 2026,
                            "form": "10-Q",
                            "accn": "0001696556-26-000025",
                            "frame": "CY2026Q2",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "OFRM", period="quarterly")
        by_year_quarter = {(r["fiscal_year"], r["fiscal_period"]): r for r in rows}

        assert by_year_quarter[(2026, "Q1")]["net_income_loss"] == -15_811_000
        assert by_year_quarter[(2026, "Q2")]["net_income_loss"] == -4_950_000

    def test_cumulative_duration_fact_still_excluded_via_span_tiebreak(self):
        """Guard against over-fixing: once correctly co-located, the real quarter must
        still beat a same-fp cumulative duration fact via the pre-existing span tiebreak."""
        facts = {
            "us-gaap": {
                "NetIncomeLoss": _concept(
                    [
                        {
                            "start": "2026-01-01",
                            "end": "2026-06-30",
                            "val": -20_761_000,
                            "filed": "2026-08-06",
                            "fp": "Q2",
                            "fy": 2026,
                            "form": "10-Q",
                        },
                        {
                            "start": "2026-04-01",
                            "end": "2026-06-30",
                            "val": -4_950_000,
                            "filed": "2026-08-06",
                            "fp": "Q2",
                            "fy": 2026,
                            "form": "10-Q",
                            "frame": "CY2026Q2",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "OFRM", period="quarterly")
        by_year_quarter = {(r["fiscal_year"], r["fiscal_period"]): r for r in rows}

        assert by_year_quarter[(2026, "Q2")]["net_income_loss"] == -4_950_000

    def test_non_december_fye_cumulative_comparative_does_not_falsely_trigger_self_consistency(self):
        """DXC-class guard: a non-December-FYE filer's own cumulative comparative facts must
        never be mistaken for genuine December-FYE self-consistency evidence.

        Modeled on DXC's real NetCashProvidedByUsedInOperatingActivities data (FYE March 31,
        fiscal Q1 = Apr-Jun). Without the 80-100 day span gate on the self-consistency check,
        the ~183-day H1-2017 comparative fact below (re-tagged fp="Q3" by a much later filing,
        end month 09 coincidentally mapping to "Q3" under the calendar-quarter convention)
        would wrongly flip has_december_fiscal_year_end to True, corrupting the real Q1
        (Apr-Jun) fact into the Q2 bucket and letting it clobber the real Q2 (cumulative)
        value via the shorter-span tiebreak.
        """
        facts = {
            "us-gaap": {
                "NetCashProvidedByUsedInOperatingActivities": _concept(
                    [
                        # The false-self-consistency bait: an 183-day H1 comparative,
                        # re-tagged with a LATER filing's own fp="Q3" - end month (09)
                        # coincidentally equals "Q3" under the calendar mapping, but this
                        # is not evidence of a real December fiscal year end.
                        {
                            "start": "2017-04-01",
                            "end": "2017-09-30",
                            "val": 1_204_000_000,
                            "filed": "2019-02-08",
                            "fp": "Q3",
                            "fy": 2019,
                            "form": "10-Q",
                        },
                        # The real, correctly-tagged fiscal Q1 (Apr-Jun) - a genuine
                        # 90-day discrete quarter under DXC's own (non-calendar) fiscal
                        # calendar, must NOT be relabeled into the Q2 bucket.
                        {
                            "start": "2019-04-01",
                            "end": "2019-06-30",
                            "val": -66_000_000,
                            "filed": "2019-08-09",
                            "fp": "Q1",
                            "fy": 2020,
                            "form": "10-Q",
                        },
                        # The real fiscal Q2 (Apr-Sep cumulative, DXC discloses cash flow
                        # only as fiscal-YTD) - must win the Q2 bucket.
                        {
                            "start": "2019-04-01",
                            "end": "2019-09-30",
                            "val": 1_585_000_000,
                            "filed": "2019-11-12",
                            "fp": "Q2",
                            "fy": 2020,
                            "form": "10-Q",
                        },
                    ]
                ),
                "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations": _concept([]),
                "NetCashProvidedByUsedInInvestingActivities": _concept([]),
                "NetCashProvidedByUsedInFinancingActivities": _concept([]),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_cash_flow(client, "DXC", period="quarterly")
        by_year_quarter = {(r["fiscal_year"], r["fiscal_period"]): r for r in rows}

        assert by_year_quarter[(2019, "Q1")]["net_cash_provided_by_used_in_operating_activities"] == -66_000_000
        assert by_year_quarter[(2019, "Q2")]["net_cash_provided_by_used_in_operating_activities"] == 1_585_000_000
