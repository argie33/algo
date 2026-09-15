"""Regression test for a cross-concept fiscal-year-end conflict in
_aggregate_concepts_detect_cross_concept_fye_conflict()/_aggregate_concepts
(utils/external/sec_statements_aggregate.py):

Live-verified 2026-09-15 via Summit Therapeutics (SMMT, CIK 0001599298) real SEC
companyfacts JSON: SMMT converted from a UK foreign-private-issuer (20-F/6-K filings, real
FYE January 31, ifrs-full taxonomy, concept "RevenueFromContractsWithCustomers") to a US
domestic filer (10-K, real FYE December 31, us-gaap taxonomy, concept
"RevenueFromContractWithCustomerExcludingAssessedTax") in 2020 - both concepts map to the
SAME canonical "revenue_from_contract_with_customer_excluding_assessed_tax" column.

`_aggregate_concepts_build_unit_context`'s existing conflicting-FYE-evidence guard only looks
at ONE concept's own history at a time - since each taxonomy's revenue concept only ever
carries genuine FY-span facts from ONE of the two regimes, each concept's own local view looks
perfectly unanimous (fye_month=1 for the old ifrs concept, fye_month=12 for the new us-gaap
concept), even though the filer's real history is genuinely two different regimes.

`_aggregate_concepts_resolve_entry_period`'s non-December-FYE quarter year-shift correction
then confidently relabels the OLD regime's real Feb-Apr/May-Jul 2018 quarters as
fiscal_year=2019 (correct under the OLD regime's own January-FYE numbering) - which silently
collides with the NEW regime's own real calendar-2019 Q1/Q2 facts computing to the exact same
(2019, Q1)/(2019, Q2) row keys, overwriting the real, much smaller, current-regime revenue
with the stale, much larger, old-regime GBP-converted figure.

Fixed by scanning every concept's genuine FY-span facts across BOTH taxonomies before any
per-concept quarter-year correction is trusted: more than one distinct fiscal-year-end month
anywhere in the filer's real history suppresses the correction for every concept, not just the
one(s) whose own local view happens to disagree with itself.
"""

from utils.external.sec_income_statement import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0001599298"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict], unit: str = "USD") -> dict:
    return {"units": {unit: entries}}


# OLD regime: real FYE January 31, ifrs-full taxonomy, GBP-denominated (converted to USD
# downstream by the real pipeline - values here are already the real post-conversion USD
# amounts observed live, so the test doesn't need to exercise FX conversion itself).
_OLD_REGIME_ENTRIES = [
    {
        # Genuine ~365-day FY span, real FYE January 31 - the signal that used to make
        # fye_month=1 look unanimous when only this concept's own history was considered.
        "start": "2017-02-01",
        "end": "2018-01-31",
        "val": 33_400_000,
        "accn": "0001599298-19-000008",
        "fy": 2019,
        "fp": "FY",
        "form": "20-F",
        "filed": "2019-04-30",
    },
    {
        # Real Q1 of the OLD regime's "FY2019" (Feb2018-Jan2019, real FYE Jan 31) - period
        # Feb-Apr 2018, correctly relabeled fiscal_year=2019 UNDER THE OLD REGIME's own
        # numbering by the existing non-December-FYE correction.
        "start": "2018-02-01",
        "end": "2018-04-30",
        "val": 5_319_893.99,
        "accn": "0001599298-19-000011",
        "fy": 2020,
        "fp": "Q1",
        "form": "6-K",
        "filed": "2019-06-12",
        "frame": "CY2018Q1",
    },
    {
        # Real Q2 of the OLD regime's "FY2019" - period May-Jul 2018. This is the value that
        # collided with the NEW regime's real calendar-Q2-2019 figure before the fix.
        "start": "2018-05-01",
        "end": "2018-07-31",
        "val": 49_930_283.34,
        "accn": "0001599298-19-000017",
        "fy": 2020,
        "fp": "Q2",
        "form": "6-K",
        "filed": "2019-08-14",
        "frame": "CY2018Q2",
    },
]

# NEW regime: real FYE December 31, us-gaap taxonomy, USD-denominated.
_NEW_REGIME_ENTRIES = [
    {
        # Genuine ~365-day FY span, real FYE December 31 - conflicts with the OLD regime's
        # January FYE once BOTH concepts' histories are considered together.
        "start": "2020-01-01",
        "end": "2020-12-31",
        "val": 860_000,
        "accn": "0001599298-21-000011",
        "fy": 2020,
        "fp": "FY",
        "form": "10-K",
        "filed": "2021-03-31",
    },
    {
        # Real calendar Q2 2019 - the correct, current-regime value that a stale old-regime
        # figure must not overwrite once both are bucketed under fiscal_year=2019. Sourced
        # from a 10-Q (a primary-statement form the real pipeline trusts for quarterly
        # extraction) - the real SMMT filing only ever tagged this exact fact via an 8-K
        # conversion filing, which the pipeline correctly doesn't trust as a quarterly source
        # on its own (unrelated to this fix); using a 10-Q here isolates the cross-concept
        # FYE-conflict behavior this test targets from that separate, pre-existing form-trust
        # rule.
        "start": "2019-04-01",
        "end": "2019-06-30",
        "val": 156_000,
        "accn": "0001599298-20-000043",
        "fy": 2020,
        "fp": "Q2",
        "form": "10-Q",
        "filed": "2020-09-29",
        "frame": "CY2019Q2",
    },
]


class TestCrossConceptFyeConflict:
    def test_smmt_old_regime_quarter_does_not_overwrite_new_regime_quarter(self):
        facts = {
            "us-gaap": {"RevenueFromContractWithCustomerExcludingAssessedTax": _concept(_NEW_REGIME_ENTRIES)},
            "ifrs-full": {"RevenueFromContractsWithCustomers": _concept(_OLD_REGIME_ENTRIES, unit="USD")},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "SMMT", period="quarterly")

        fy2019_q2 = [r for r in rows if r.get("fiscal_year") == 2019 and r.get("fiscal_period") == "Q2"]
        assert fy2019_q2, f"expected a fiscal_year=2019 Q2 row, got {rows!r}"
        value = fy2019_q2[0].get("revenue_from_contract_with_customer_excluding_assessed_tax")
        assert value == 156_000, (
            f"Expected SMMT's real calendar Q2 2019 revenue $156,000 (the current-regime "
            f"us-gaap fact), got {value!r} - a value of $49,930,283.34 means the old-regime "
            f"GBP fact won the collision and the cross-concept FYE-conflict regression is back"
        )

    def test_single_regime_filer_unaffected(self):
        """A filer with only ONE fiscal-year-end regime in its whole history (no cross-concept
        conflict) must still get the existing non-December-FYE quarter-year correction - this
        fix must not blanket-disable that correction for every filer."""
        single_regime_entries = [
            {
                "start": "2016-10-01",
                "end": "2017-09-30",
                "val": 31_400_000,
                "accn": "0000000001-17-000001",
                "fy": 2017,
                "fp": "FY",
                "form": "10-K",
                "filed": "2017-11-15",
            },
            {
                # Real Q1 of FY2017 (Oct-Dec 2016, real FYE September 30) - end date falls in
                # calendar 2016, must be relabeled fiscal_year=2017 by the existing correction.
                "start": "2016-10-01",
                "end": "2016-12-31",
                "val": 4_365_000,
                "accn": "0000000001-17-000002",
                "fy": 2017,
                "fp": "Q1",
                "form": "10-Q",
                "filed": "2017-02-05",
            },
        ]
        facts = {
            "us-gaap": {"Revenues": _concept(single_regime_entries)},
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "TESTCO", period="quarterly")

        fy2017_q1 = [r for r in rows if r.get("fiscal_year") == 2017 and r.get("fiscal_period") == "Q1"]
        assert fy2017_q1, f"expected the Oct-Dec 2016 quarter relabeled fiscal_year=2017, got {rows!r}"
        assert fy2017_q1[0].get("revenues") == 4_365_000
