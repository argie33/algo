"""Regression test for a non-December-fiscal-year-end variant of the frame-derived quarterly
fp bug in _aggregate_concepts_resolve_entry_period (utils/external/sec_statements_entry_resolution.py)
- goal session 2026-09-16, data-patrol/XBRL findings sweep, AGYS live-confirmed via real SEC
companyfacts JSON (CIK 0000078749).

The 2026-09-15 ARQ fix (test_sec_statements_quarterly_fp_derivation_from_frame_arq_20260915.py)
added a fallback that derives a duration fact's fiscal quarter from SEC's own `frame` tag
(e.g. 'CY2017Q4') when the fact's own `fp` isn't already Q1-Q4 - but SEC's frame always names
the CALENDAR quarter, which only equals the filer's fiscal quarter for a December fiscal-year-end
filer. For any other fiscal-year-end month, that fallback silently mislabeled the wrong quarter.

Live-confirmed via Agilysys (AGYS, real FYE March 31): its FY2019 10-K's "Selected Quarterly
Financial Data" footnote re-cites Oct-Dec 2017 revenue ($31,310,000 - a genuine discrete
quarter, AGYS's own real fiscal Q3 since its fiscal year runs April-March) tagged fp='FY' (the
filing's own period) with frame='CY2017Q4' (SEC's calendar framing). The pre-fix code took
`_frame[7]` ('4') as the fiscal quarter number directly, landing this real Q3 revenue in a
synthetic fiscal_quarter=4 bucket instead - seeding a Q4 row with the wrong period_end that
stayed wrong even after the unrelated FY-minus-9mo sweep (loaders/helpers/
financial_statements_q4_sweeps.py) later overwrote its *value* (the sweep only ever UPDATEs an
existing row, never touches period_end).

Fixed by translating the frame's calendar-quarter number into the filer's real fiscal-quarter
number via fye_month before using it, the same end-month-relative-to-fye_month cadence already
trusted for this file's non-Dec fiscal-year quarter/year correction.
"""

from utils.external.sec_income_statement import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000078749"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


# Real AGYS (Agilysys) RevenueFromContractWithCustomerExcludingAssessedTax facts, March 31 FYE.
_AGYS_REVENUE_ENTRIES = [
    # Unanimous FY-tagged annual facts (real full-year Apr-Mar spans) - establishes
    # fye_month=3 unambiguously.
    {
        "start": "2019-04-01",
        "end": "2020-03-31",
        "val": 160757000,
        "fp": "FY",
        "form": "10-K",
        "fy": 2022,
        "accn": "0000950170-22-010512",
        "filed": "2022-05-23",
    },
    {
        "start": "2020-04-01",
        "end": "2021-03-31",
        "val": 137176000,
        "fp": "FY",
        "form": "10-K",
        "fy": 2022,
        "accn": "0000950170-22-010512",
        "filed": "2022-05-23",
    },
    {
        "start": "2021-04-01",
        "end": "2022-03-31",
        "val": 162636000,
        "fp": "FY",
        "form": "10-K",
        "fy": 2022,
        "accn": "0000950170-22-010512",
        "filed": "2022-05-23",
    },
    {
        "start": "2022-04-01",
        "end": "2023-03-31",
        "val": 198065000,
        "fp": "FY",
        "form": "10-K",
        "fy": 2023,
        "accn": "0000950170-23-023196",
        "filed": "2023-05-19",
    },
    # The mislabeling case: a "Selected Quarterly Financial Data" comparative re-cited inside
    # the FY2019 10-K, tagged fp='FY' (the filing's own period) with a calendar-quarter frame.
    # This is AGYS's own real, genuine, discrete fiscal Q3 (Oct-Dec, since AGYS's fiscal year
    # runs April-March) - not fiscal Q4.
    {
        "start": "2017-10-01",
        "end": "2017-12-31",
        "val": 31310000,
        "fp": "FY",
        "form": "10-K",
        "fy": 2019,
        "accn": "0000078749-19-000021",
        "filed": "2019-05-24",
        "frame": "CY2017Q4",
    },
]


class TestFrameDerivedFpNonDecemberFyeAgys:
    def test_calendar_q4_frame_maps_to_real_fiscal_q3_for_march_fye_filer(self):
        facts = {"us-gaap": {"RevenueFromContractWithCustomerExcludingAssessedTax": _concept(_AGYS_REVENUE_ENTRIES)}}
        client = _FakeClient(facts)

        rows = get_income_statement(client, "AGYS", period="quarterly")
        by_key = {(r["fiscal_year"], r["fiscal_period"]): r for r in rows}

        _field = "revenue_from_contract_with_customer_excluding_assessed_tax"

        # AGYS's fiscal year is labeled by the calendar year it ends in (FY2018 = Apr2017-Mar2018),
        # so the Oct-Dec 2017 quarter (fye_month=3, end_month=12 > 3) belongs to FY2018.
        assert (2018, "Q3") in by_key, f"expected AGYS's real fiscal Q3 2018 bucket, got keys {sorted(by_key)!r}"
        assert by_key[(2018, "Q3")][_field] == 31310000
        assert by_key[(2018, "Q3")]["period_end"] == "2017-12-31"

        # The pre-fix bug landed this fact under fiscal_quarter=4 instead - must not recur.
        assert (2018, "Q4") not in by_key or by_key[(2018, "Q4")].get(_field) != 31310000, (
            "AGYS's real fiscal-Q3 revenue was mislabeled into a synthetic fiscal-Q4 bucket - "
            "the frame-derived quarterly fp regression for non-December fiscal-year-end filers is back"
        )
