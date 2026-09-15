"""Regression test for a quarterly fp-derivation gap in
_aggregate_concepts_resolve_entry_period() (utils/external/sec_statements_entry_resolution.py):

Live-verified 2026-09-15 via Arq Inc (ARQ, CIK 0001515156) real SEC companyfacts JSON: Revenues
for start=2013-04-01/end=2013-06-30 (ARQ's real Q2 2013) has the ORIGINALLY-FILED 2013 10-Q
(accn 0001564590-13-000293, filed 2013, val=$58,930,000, fp='Q2', no frame) - then ARQ's own
2016 10-K/A (accn 0001515156-16-000074, a genuine restatement) re-cites the SAME period as a
comparative duration fact at the CORRECTED value $6,427,000 (~9x smaller), tagged fp='FY' (the
filing's own reporting period) with frame='CY2013Q2' - SEC's frames API independently confirming
this is the real discrete quarter.

_aggregate_concepts_resolve_entry_period's quarterly branch only derived a usable fp for
duration facts whose SEC fp tag already fell in Q1-Q4; a duration fact tagged fp='FY' (common
for a comparative re-cited inside an annual filing) was unconditionally dropped, since the
fallback derivation only handled instant facts (`not start_date`). This silently discarded the
correct, later, frame-confirmed restated value and left the stale, wildly-wrong original 10-Q
value as the only candidate ever considered for the (2013, Q2) bucket - inflating summed
quarterly revenue to ~10x the audited annual total (the real-world
quarterly_revenue_sum_vs_annual_extreme finding this test guards against).

Fixed by deriving fp from the SEC frame tag itself ('CYyyyyQn') for a duration fact whose own fp
isn't already Q1-Q4, narrowly scoped to a genuine single-quarter span (80-100 days) so a
cumulative fact sharing the 'CYyyyyQn' prefix can't slip through.
"""

from utils.external.sec_income_statement import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0001515156"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


_ARQ_REVENUE_ENTRIES = [
    {
        "start": "2013-04-01",
        "end": "2013-06-30",
        "val": 58_930_000,
        "accn": "0001564590-13-000293",
        "fy": 2013,
        "fp": "Q2",
        "form": "10-Q",
        "filed": "2013-08-08",
    },
    {
        "start": "2013-04-01",
        "end": "2013-06-30",
        "val": 6_427_000,
        "accn": "0001515156-16-000074",
        "fy": 2014,
        "fp": "FY",
        "form": "10-K/A",
        "filed": "2016-03-15",
        "frame": "CY2013Q2",
    },
]


class TestQuarterlyFpDerivationFromFrame:
    def test_arq_recovers_restated_quarter_from_frame_tagged_fy_form_duration_fact(self):
        facts = {"us-gaap": {"Revenues": _concept(_ARQ_REVENUE_ENTRIES)}, "ifrs-full": {}}
        client = _FakeClient(facts)

        rows = get_income_statement(client, "ARQ", period="quarterly")

        matching = [r for r in rows if r.get("revenues") in (58_930_000, 6_427_000)]
        assert matching, f"expected a row for the 2013-04-01..2013-06-30 period, got {rows!r}"
        assert all(r["revenues"] == 6_427_000 for r in matching), (
            f"Expected ARQ's restated Q2 2013 revenue $6,427,000 (from the frame-tagged 10-K/A "
            f"comparative), got {[r['revenues'] for r in matching]!r} - the stale pre-restatement "
            f"$58,930,000 value means the frame-derived quarterly fp regression is back"
        )

    def test_cumulative_fact_sharing_frame_prefix_is_not_misclassified_as_discrete_quarter(self):
        """A ~181-day H1 cumulative fact that happens to carry a 'CYyyyyQn'-shaped frame must
        NOT be accepted as a discrete quarter via the new frame-derivation path - only a genuine
        80-100 day span qualifies."""
        facts = {
            "us-gaap": {
                "Revenues": _concept(
                    [
                        {
                            "start": "2013-04-01",
                            "end": "2013-06-30",
                            "val": 6_427_000,
                            "accn": "0001515156-16-000074",
                            "fy": 2013,
                            "fp": "Q2",
                            "form": "10-Q",
                            "filed": "2013-08-08",
                        },
                        {
                            "start": "2013-01-01",
                            "end": "2013-06-30",
                            "val": 127_244_000,
                            "accn": "0001564590-13-000293",
                            "fy": 2014,
                            "fp": "FY",
                            "form": "10-K/A",
                            "filed": "2016-03-15",
                            "frame": "CY2013Q2",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "ARQ", period="quarterly")
        matching = [r for r in rows if r.get("revenues") is not None]
        assert not any(r["revenues"] == 127_244_000 for r in matching), (
            f"the 181-day H1 cumulative fact must not be accepted as a discrete quarter just "
            f"because it carries a 'CYyyyyQn' frame, got {[r['revenues'] for r in matching]!r}"
        )
