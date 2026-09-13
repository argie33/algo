"""Regression test for the 2026-09-13 fix in utils/external/sec_statements_unit_context.py's
`_aggregate_concepts_build_unit_context` (goal session: revenue-identity reload-verified bug
dig, QCOM/SBUX live-confirmed via real SEC companyfacts JSON).

The 2026-09-02 `has_december_fiscal_year_end` self-consistency fallback (see
test_sec_statements_quarterly_duration_fact_comparative_fp_aliasing_20260902.py) already
narrows out one false-positive shape (a multi-month CUMULATIVE comparative fact landing on a
calendar-quarter-end month by coincidence, DXC-confirmed) via an 80-100 day span gate. It did
NOT narrow out a second, distinct false-positive shape: a genuinely single-quarter-length
(80-100 day) duration fact that is STILL a mistagged comparative echo from a LATER filing, not
this filer's own current-period fact.

Live-confirmed via QCOM (CIK 0000804328, real fiscal year end late September, never December):
a us-gaap:Revenues fact spanning 2017-12-25 to 2018-03-25 (90 days - a genuine single-quarter
span) is tagged fp="Q1"/fy=2019/filed 2019-01-30 - a later filing's own comparative echo of
what was, in QCOM's real Oct-Sep fiscal calendar, actually fiscal Q2, inheriting that later
filing's own fp/fy label. Because its end-month (03) coincidentally satisfies the calendar-
quarter mapping for its (wrong) fp="Q1" tag AND its span passes the existing 80-100 day gate,
it flipped has_december_fiscal_year_end to True - which then made the AMZN-rolling-window
guard in sec_statements_entry_resolution.py reject every one of QCOM's real annual "Revenues"
facts (end dates in September, month != 12), including FY2025's real $44,284,000,000 -
confirmed via scripts/verify_and_fix_revenue_identity.py's REELOAD_NO_CHANGE QCOM row (stored
$639M, unchanged by a real production reload) before this fix.

Fix: require the matching entry's `filed` date to fall within 120 days of its own `end` date
(a generous buffer over the longest real 10-Q deadline) before trusting it as
self-consistency evidence - a genuine current-period quarterly fact is always filed shortly
after its own period ends; a fact filed many months later is, by construction, riding along
in a later filing as someone else's comparative column.
"""

from utils.external.sec_statements import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000804328"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


class TestMistaggedSingleQuarterComparativeFyeFalsePositive:
    def test_late_filed_single_quarter_match_does_not_flip_december_fye(self) -> None:
        facts = {
            "us-gaap": {
                "Revenues": _concept(
                    [
                        # The false-self-consistency bait: a genuine 90-day span, end-month
                        # (03) matches the calendar-quarter mapping for its fp="Q1" tag, but
                        # filed 311 days after its own end date - a later filing's
                        # comparative echo, not QCOM's own current-period Q1 fact.
                        {
                            "start": "2017-12-25",
                            "end": "2018-03-25",
                            "val": 5_220_000_000,
                            "filed": "2019-01-30",
                            "fp": "Q1",
                            "fy": 2019,
                            "form": "10-Q",
                            "accn": "0001728949-19-000012",
                        },
                        # QCOM's real FY2025 10-K annual total - fiscal year ends in
                        # September, never December. Must survive.
                        {
                            "start": "2024-09-30",
                            "end": "2025-09-28",
                            "val": 44_284_000_000,
                            "filed": "2025-11-05",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                            "accn": "0000804328-25-000085",
                            "frame": "CY2025",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "QCOM", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["revenues"] == 44_284_000_000

    def test_promptly_filed_single_quarter_match_still_flips_december_fye(self) -> None:
        """Guard against over-fixing: a genuine, promptly-filed single-quarter match (like
        AMZN's/OFRM's real Q1 facts) must still establish has_december_fiscal_year_end."""
        facts = {
            "us-gaap": {
                "NetIncomeLoss": _concept(
                    [
                        {
                            "start": "2025-01-01",
                            "end": "2025-03-31",
                            "val": 17_127_000_000.0,
                            "filed": "2025-05-01",
                            "fp": "Q1",
                            "fy": 2025,
                            "form": "10-Q",
                            "accn": "0001018724-25-000001",
                        },
                        # A rolling trailing-twelve-month MD&A disclosure - must still be
                        # rejected from the FY2025 bucket by the pre-existing December-end
                        # rolling-window guard once has_december_fiscal_year_end is (still)
                        # correctly established True by the promptly-filed Q1 fact above.
                        {
                            "start": "2024-07-01",
                            "end": "2025-06-30",
                            "val": 70_623_000_000.0,
                            "filed": "2026-08-01",
                            "fp": None,
                            "fy": None,
                            "form": "10-Q",
                            "accn": "0001018724-26-000002",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)
        client.symbol_to_cik = lambda symbol: "0001018724"  # type: ignore[method-assign]

        rows = get_income_statement(client, "AMZN", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert "net_income_loss" not in by_year.get(2025, {})
