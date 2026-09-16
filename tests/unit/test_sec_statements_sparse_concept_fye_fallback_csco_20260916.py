"""Regression tests for same-run fiscal-year collisions in
_aggregate_concepts_detect_cross_concept_fye() / _aggregate_concepts_apply_cross_concept_fye_override()
(utils/external/sec_statements_aggregate.py), covering two distinct shapes: a SPARSE concept's
own fye_month detection coming back None (CSCO), and a concept's own detection coming back
CONFIDENTLY WRONG due to a stray instant-shaped fact (ALNY).

Live-verified 2026-09-16 via Cisco Systems (CSCO, CIK 0000858877) real SEC companyfacts JSON:
CSCO's real fiscal-year-end is July (fye_month=7). Its richly-tagged "SalesRevenueNet" concept
has enough genuine FY-span facts to confidently detect fye_month=7 and correctly apply the
non-December-FYE quarter year-shift correction. Its "ProfitLoss" concept, however, was tagged
in only ONE filing ever (two quarterly facts, no FY-span fact at all) - nowhere near enough
evidence for `_aggregate_concepts_build_unit_context` to determine fye_month on its own, so it
fell back to fye_month=None (no correction applied).

Two genuinely different real quarters then collided onto the identical (fiscal_year=2009,
fiscal_period='Q1') row key:
- ProfitLoss's real fiscal Q1 FY2009 fact (period 2008-07-27/2008-10-25, val=2,201,000,000):
  naive end-date-year bucket is 2008, but this concept's own local fye_month WAS actually
  confidently knowable from the broader symbol context - just not from this concept's own
  sparse local view.
- ProfitLoss's real fiscal Q1 FY2010 fact (period 2009-07-26/2009-10-24, val=1,787,000,000):
  naive end-date-year bucket is 2009 - with no correction applied (since this concept's own
  local fye_month was None), this WRONG naive bucket collided with the row above's CORRECT
  corrected bucket.

Fixed by falling back to the single cross-concept-agreed fye_month (the same evidence
`_aggregate_concepts_detect_cross_concept_fye`'s conflict check already computes) whenever a
concept's own local detection has no evidence of its own - never overriding a concept's own
confident value, and never applied when the cross-concept evidence is itself conflicting.
"""

from utils.external.sec_income_statement import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000858877"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict], unit: str = "USD") -> dict:
    return {"units": {unit: entries}}


# Richly-tagged concept: enough genuine FY-span facts across the symbol's history for
# fye_month=7 (real FYE July) to be confidently determined on its own.
_SALES_REVENUE_NET_ENTRIES = [
    {
        # Genuine ~365-day FY span, real FYE July 31 (365 days here, close enough to pass the
        # genuine-FY-span duration check) - the evidence that makes fye_month=7 confidently
        # knowable for this concept, and (via the cross-concept scan) for the whole symbol.
        "start": "2008-07-27",
        "end": "2009-07-25",
        "val": 36_117_000_000,
        "accn": "0001193125-09-198702",
        "fy": 2009,
        "fp": "FY",
        "form": "10-K",
        "filed": "2009-09-15",
    },
    {
        # Real fiscal Q1 FY2009 (Aug-Oct 2008) - naive end-date-year is 2008, correctly
        # relabeled fiscal_year=2009 by the existing non-December-FYE correction.
        "start": "2008-07-27",
        "end": "2008-10-25",
        "val": 10_331_000_000,
        "accn": "0001193125-09-237055",
        "fy": 2010,
        "fp": "Q1",
        "form": "10-Q",
        "filed": "2009-11-18",
        "frame": "CY2008Q3",
    },
    {
        # Real fiscal Q1 FY2010 (Aug-Oct 2009) - naive end-date-year is 2009, correctly
        # relabeled fiscal_year=2010 by the existing non-December-FYE correction.
        "start": "2009-07-26",
        "end": "2009-10-24",
        "val": 9_815_000_000,
        "accn": "0001193125-09-237055",
        "fy": 2010,
        "fp": "Q1",
        "form": "10-Q",
        "filed": "2009-11-18",
        "frame": "CY2009Q3",
    },
]

# Sparse concept: tagged in only ONE filing ever, no FY-span fact of its own - not enough
# local evidence for this concept alone to determine fye_month. Same two real quarters as
# above, same values as CSCO's real ProfitLoss facts.
_PROFIT_LOSS_ENTRIES = [
    {
        "start": "2008-07-27",
        "end": "2008-10-25",
        "val": 2_201_000_000,
        "accn": "0001193125-09-237055",
        "fy": 2010,
        "fp": "Q1",
        "form": "10-Q",
        "filed": "2009-11-18",
        "frame": "CY2008Q3",
    },
    {
        "start": "2009-07-26",
        "end": "2009-10-24",
        "val": 1_787_000_000,
        "accn": "0001193125-09-237055",
        "fy": 2010,
        "fp": "Q1",
        "form": "10-Q",
        "filed": "2009-11-18",
        "frame": "CY2009Q3",
    },
]


class TestSparseConceptFyeFallback:
    def test_sparse_concept_does_not_collide_two_real_quarters(self):
        facts = {
            "us-gaap": {
                "SalesRevenueNet": _concept(_SALES_REVENUE_NET_ENTRIES),
                "ProfitLoss": _concept(_PROFIT_LOSS_ENTRIES),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "CSCO", period="quarterly")

        fy2009_q1 = [r for r in rows if r.get("fiscal_year") == 2009 and r.get("fiscal_period") == "Q1"]
        fy2010_q1 = [r for r in rows if r.get("fiscal_year") == 2010 and r.get("fiscal_period") == "Q1"]

        assert len(fy2009_q1) == 1, f"expected exactly one fiscal_year=2009 Q1 row, got {fy2009_q1!r}"
        assert len(fy2010_q1) == 1, f"expected exactly one fiscal_year=2010 Q1 row, got {fy2010_q1!r}"

        assert fy2009_q1[0].get("profit_loss") == 2_201_000_000, (
            f"expected FY2009 Q1 ProfitLoss=2,201,000,000, got {fy2009_q1[0].get('profit_loss')!r} - "
            "a value of 1,787,000,000 here means the two real quarters collided again"
        )
        assert fy2010_q1[0].get("profit_loss") == 1_787_000_000, (
            f"expected FY2010 Q1 ProfitLoss=1,787,000,000, got {fy2010_q1[0].get('profit_loss')!r}"
        )
        assert fy2009_q1[0].get("period_end") == "2008-10-25"
        assert fy2010_q1[0].get("period_end") == "2009-10-24"

    def test_conflicting_cross_concept_evidence_still_suppresses_fallback(self):
        """A concept with no local evidence must NOT get a fallback fye_month when the
        symbol's cross-concept evidence is itself conflicting (two different regimes) - the
        fallback must never fire in the same case the existing conflict-suppression guards
        against. Reuses real recognized concepts ("Revenues" us-gaap / "Revenue" ifrs, and
        "ProfitLoss" as the sparse concept) so get_income_statement's real concept list picks
        all three up, same as the module-level fixtures above."""
        conflicting_fy_span_entries = [
            {
                "start": "2017-02-01",
                "end": "2018-01-31",
                "val": 33_400_000,
                "accn": "0000000002-19-000001",
                "fy": 2019,
                "fp": "FY",
                "form": "20-F",
                "filed": "2019-04-30",
            },
        ]
        another_fy_span_entries = [
            {
                "start": "2020-01-01",
                "end": "2020-12-31",
                "val": 860_000,
                "accn": "0000000002-21-000001",
                "fy": 2020,
                "fp": "FY",
                "form": "10-K",
                "filed": "2021-03-31",
            },
        ]
        sparse_entries = [
            {
                "start": "2018-02-01",
                "end": "2018-04-30",
                "val": 999_999,
                "accn": "0000000002-19-000002",
                "fy": 2020,
                "fp": "Q1",
                "form": "6-K",
                "filed": "2019-06-12",
                "frame": "CY2018Q1",
            },
        ]
        facts = {
            "us-gaap": {
                "Revenues": _concept(another_fy_span_entries),
                "ProfitLoss": _concept(sparse_entries),
            },
            "ifrs-full": {"Revenue": _concept(conflicting_fy_span_entries)},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "CONFLICTTEST", period="quarterly")

        sparse_rows = [r for r in rows if r.get("profit_loss") is not None]
        assert sparse_rows, f"expected a row for ProfitLoss's one fact, got {rows!r}"
        # Naive end-date-year bucket (2018), NOT relabeled - the correction must stay
        # suppressed for a concept with no local evidence when cross-concept evidence itself
        # conflicts, same as it already is for a concept WITH local (but conflicting) evidence.
        assert sparse_rows[0].get("fiscal_year") == 2018, (
            f"expected fiscal_year=2018 (uncorrected) under conflicting cross-concept evidence, "
            f"got {sparse_rows[0].get('fiscal_year')!r}"
        )


class TestConfidentButWrongLocalFyeOverridden:
    """ALNY (CIK 0001178670) real FYE is December. Its
    "RevenueFromContractWithCustomerExcludingAssessedTax" concept carries a genuine filer-side
    XBRL tagging error: an instant-shaped fact dated 2018-01-01 (frame='CY2017Q4I') that has no
    business existing on a duration/revenue concept at all.
    `_aggregate_concepts_build_unit_context`'s instant-fact FYE heuristic (built for
    balance-sheet-shaped concepts) doesn't know this concept isn't instant-shaped, and the
    single bad fact - unanimous by construction, since it's the only instant fact this concept
    has - confidently produces fye_month=1 for this ONE concept alone, even though its own
    genuine FY-duration facts (and every other income-statement concept's) unanimously agree on
    December. Real calendar Q2 2017 (end=2017-06-30) then collides with a comparative Q2 fact
    from ALNY's real FY2018 Q2 10-Q, both wrongly landing under fiscal_year=2018.
    """

    def test_stray_instant_fact_does_not_override_unanimous_duration_evidence(self):
        # Genuine FY-duration facts (all ending December) for BOTH concepts - what the
        # cross-concept scan uses to determine the correct symbol-wide month=12.
        net_income_loss_entries = [
            {
                "start": "2016-01-01",
                "end": "2016-12-31",
                "val": -206_886_000,
                "accn": "0000000003-17-000001",
                "fy": 2016,
                "fp": "FY",
                "form": "10-K",
                "filed": "2017-02-15",
            },
        ]
        revenue_entries = [
            {
                "start": "2016-01-01",
                "end": "2016-12-31",
                "val": 47_159_000,
                "accn": "0000000003-19-000001",
                "fy": 2018,
                "fp": "FY",
                "form": "10-K",
                "filed": "2019-02-14",
            },
            # The stray instant-shaped fact - no "start" - that hijacks this ONE concept's own
            # local fye_month detection to January.
            {
                "end": "2018-01-01",
                "val": 2_900_000,
                "accn": "0000000003-20-000001",
                "fy": 2019,
                "fp": "FY",
                "form": "10-K",
                "filed": "2020-02-13",
                "frame": "CY2017Q4I",
            },
            # Real calendar Q2 2017 (Apr-Jun 2017, a distinct real quarter with its own value).
            {
                "start": "2017-04-01",
                "end": "2017-06-30",
                "val": 20_000_000,
                "accn": "0000000003-17-000002",
                "fy": 2017,
                "fp": "Q2",
                "form": "10-Q",
                "filed": "2017-08-01",
                "frame": "CY2017Q2",
            },
            # Comparative echo of the SAME real Q2 2017 quarter, riding along inside ALNY's real
            # FY2018 Q2 10-Q - the collision partner before this fix.
            {
                "start": "2017-04-01",
                "end": "2017-06-30",
                "val": 20_000_000,
                "accn": "0000000003-18-000001",
                "fy": 2018,
                "fp": "Q2",
                "form": "10-Q",
                "filed": "2018-08-02",
            },
        ]
        facts = {
            "us-gaap": {
                "NetIncomeLoss": _concept(net_income_loss_entries),
                "RevenueFromContractWithCustomerExcludingAssessedTax": _concept(revenue_entries),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "ALNY", period="quarterly")

        fy2017_q2 = [r for r in rows if r.get("fiscal_year") == 2017 and r.get("fiscal_period") == "Q2"]
        fy2018_q2 = [r for r in rows if r.get("fiscal_year") == 2018 and r.get("fiscal_period") == "Q2"]

        assert len(fy2017_q2) == 1, (
            f"expected exactly one fiscal_year=2017 Q2 row (real calendar Q2 2017 must not be "
            f"relabeled 2018 by the stray instant fact), got {fy2017_q2!r}"
        )
        assert fy2017_q2[0].get("revenue_from_contract_with_customer_excluding_assessed_tax") == 20_000_000
        assert len(fy2018_q2) == 0, (
            f"expected no fiscal_year=2018 Q2 row - the comparative echo shares the exact same "
            f"(start, end) as the real 2017 Q2 fact above and correctly dedupes into that same "
            f"row by period rather than surviving as a second, mislabeled 2018 row, got {fy2018_q2!r}"
        )
