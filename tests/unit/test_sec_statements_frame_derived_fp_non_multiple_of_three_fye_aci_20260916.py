"""Regression test for a non-multiple-of-3 fiscal-year-end variant of the frame-derived
quarterly fp bug in _aggregate_concepts_resolve_entry_period (utils/external/
sec_statements_entry_resolution.py) - goal session 2026-09-16, data-issue fix-through sweep,
ACI (Albertsons Companies, CIK 0001646972) live-confirmed via real SEC companyfacts JSON.

The 2026-09-16 AGYS fix (test_sec_statements_frame_derived_fp_non_december_fye_agys_20260916.py)
translated SEC's calendar-quarter frame into the filer's real fiscal quarter via
`_calendar_quarter_end_month = int(_frame[7]) * 3` followed by
`((_calendar_quarter_end_month - fye_month - 1) % 12) // 3 + 1`. That formula only produces a
correct answer when `fye_month` is itself a multiple of 3 (a calendar-quarter-aligned fiscal
year end, e.g. AGYS's March 31) - it coincidentally worked for AGYS but silently mislabels
quarters for any filer whose fiscal year end is NOT a multiple of 3, such as Albertsons
(fiscal year end the last Saturday of February, fye_month=2).

Live-confirmed via ACI's real RevenueFromContractWithCustomerExcludingAssessedTax facts: a
genuine discrete Jun18-Sep9 2017 quarter (ACI's real fiscal Q2 of FY2018, frame='CY2017Q3') was
placed in fiscal Q3 instead of Q2, and a genuine discrete Dec2016-Feb2017 quarter (ACI's real
fiscal Q4 of FY2017, frame='CY2017Q1') was placed in fiscal Q1 instead of Q4.

Fixed by anchoring on the CALENDAR quarter that fye_month itself falls in (not fye_month's raw
value), so fiscal-year-end months sharing a calendar quarter (Feb/Mar, May/Jun, Aug/Sep,
Nov/Dec) get identical, correct treatment.
"""

from utils.external.sec_income_statement import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0001646972"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


# Real ACI (Albertsons) RevenueFromContractWithCustomerExcludingAssessedTax facts, fiscal
# year end the last Saturday of February (fye_month=2).
_ACI_REVENUE_ENTRIES = [
    # Unanimous FY-tagged annual facts (real full-year Feb-Feb spans) - establishes
    # fye_month=2 unambiguously.
    {
        "start": "2017-02-26",
        "end": "2018-02-24",
        "val": 59924600000,
        "fp": "FY",
        "form": "10-K",
        "fy": 2018,
        "accn": "0001646972-19-000036",
        "filed": "2019-04-23",
    },
    {
        "start": "2018-02-25",
        "end": "2019-02-23",
        "val": 60534500000,
        "fp": "FY",
        "form": "10-K",
        "fy": 2019,
        "accn": "0001646972-19-000036",
        "filed": "2019-04-23",
    },
    # The mislabeling case: discrete quarterly comparatives re-cited inside the FY2019 10-K,
    # tagged fp='FY' (the filing's own period) with calendar-quarter frames. Both are ACI's
    # own real, genuine, discrete fiscal quarters (fiscal year runs Feb/Mar-Feb/Mar).
    {
        "start": "2017-06-18",
        "end": "2017-09-09",
        "val": 13831700000,
        "fp": "FY",
        "form": "10-K",
        "fy": 2019,
        "accn": "0001646972-19-000036",
        "filed": "2019-04-23",
        "frame": "CY2017Q3",
    },
    {
        "start": "2016-12-04",
        "end": "2017-02-25",
        "val": 13816600000,
        "fp": "FY",
        "form": "10-K",
        "fy": 2018,
        "accn": "0001646972-18-000017",
        "filed": "2018-04-24",
        "frame": "CY2017Q1",
    },
]


class TestFrameDerivedFpNonMultipleOfThreeFyeAci:
    def test_calendar_q3_frame_maps_to_real_fiscal_q2_for_february_fye_filer(self):
        facts = {"us-gaap": {"RevenueFromContractWithCustomerExcludingAssessedTax": _concept(_ACI_REVENUE_ENTRIES)}}
        client = _FakeClient(facts)

        rows = get_income_statement(client, "ACI", period="quarterly")
        by_key = {(r["fiscal_year"], r["fiscal_period"]): r for r in rows}

        _field = "revenue_from_contract_with_customer_excluding_assessed_tax"

        # end_month=9 > fye_month=2, so this quarter belongs to FY2018 (labeled by the
        # calendar year the fiscal year ends in).
        assert (2018, "Q2") in by_key, f"expected ACI's real fiscal Q2 2018 bucket, got keys {sorted(by_key)!r}"
        assert by_key[(2018, "Q2")][_field] == 13831700000

        assert (2018, "Q3") not in by_key or by_key[(2018, "Q3")].get(_field) != 13831700000, (
            "ACI's real fiscal-Q2 revenue was mislabeled into a synthetic fiscal-Q3 bucket - "
            "the frame-derived quarterly fp regression for non-multiple-of-3 FYE filers is back"
        )

    def test_calendar_q1_frame_maps_to_real_fiscal_q4_for_february_fye_filer(self):
        facts = {"us-gaap": {"RevenueFromContractWithCustomerExcludingAssessedTax": _concept(_ACI_REVENUE_ENTRIES)}}
        client = _FakeClient(facts)

        rows = get_income_statement(client, "ACI", period="quarterly")
        by_key = {(r["fiscal_year"], r["fiscal_period"]): r for r in rows}

        _field = "revenue_from_contract_with_customer_excluding_assessed_tax"

        # end_month=2 == fye_month=2, so this quarter belongs to FY2017 (the fiscal year it
        # closes out), not FY2018.
        assert (2017, "Q4") in by_key, f"expected ACI's real fiscal Q4 2017 bucket, got keys {sorted(by_key)!r}"
        assert by_key[(2017, "Q4")][_field] == 13816600000

        assert (2017, "Q1") not in by_key or by_key[(2017, "Q1")].get(_field) != 13816600000, (
            "ACI's real fiscal-Q4 revenue was mislabeled into a synthetic fiscal-Q1 bucket - "
            "the frame-derived quarterly fp regression for non-multiple-of-3 FYE filers is back"
        )
