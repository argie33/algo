"""Regression test for a quarterly duration-fact magnitude bug in
_aggregate_concepts_should_replace_entry() (utils/external/sec_statements_entry_resolution.py):

Live-verified 2026-09-13 via Dyadic International (DYAI, CIK 0001213809) real SEC
companyfacts JSON: RevenueFromContractWithCustomerExcludingAssessedTax for
start=2021-01-01/end=2021-03-31 (DYAI's real Q1 2021) has the ORIGINAL 2021 Q1 10-Q (accn
0001437749-21-012046, filed 2021-05-13, val=$460,520, no frame) - then DYAI's own FY2022 Q1
10-Q re-cites the SAME period as a comparative column at $460,520,000 (accn
0001437749-22-012148, filed 2022-05-12, frame="CY2021Q1"), a filer-side 1000x decimals-tag
error, not a real restatement.

The quarterly branch of _aggregate_concepts_should_replace_entry (span-based tiebreak, falling
back to plain filed-date when spans tie) had no magnitude-sanity guard at all - unlike the
sibling instant-fact and annual duration-fact frame-preference branches, which both already
guard against exactly this shape (see test_sec_statements_frame_magnitude_scale_guard_
duration_upc_20260910.py for the annual case). Since both entries here are genuine ~89-day Q1
spans, span alone can't distinguish them, so the later-filed 1000x outlier confidently won -
inflating DYAI's quarterly revenue sum ~192x above its own audited annual total and feeding
the quarterly_revenue_sum_vs_annual_extreme DataPatrol quarantine (also independently
reconfirmed via FENC's Q3 2020, $200,000 -> $200,000,000).

Fixed by porting the same magnitude-sanity guard to the quarterly branch's filed-date tiebreak:
a frame-tagged replacement whose value differs from an ALREADY-STORED value by a ratio within
1% of a clean power of 10 is rejected (smaller magnitude wins, regardless of arrival order).
"""

from utils.external.sec_income_statement import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0001213809"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


_DYAI_REVENUE_ENTRIES = [
    {
        "start": "2021-01-01",
        "end": "2021-03-31",
        "val": 460_520,
        "accn": "0001437749-21-012046",
        "fy": 2021,
        "fp": "Q1",
        "form": "10-Q",
        "filed": "2021-05-13",
    },
    {
        "start": "2021-01-01",
        "end": "2021-03-31",
        "val": 460_520_000,
        "accn": "0001437749-22-012148",
        "fy": 2022,
        "fp": "Q1",
        "form": "10-Q",
        "filed": "2022-05-12",
        "frame": "CY2021Q1",
    },
]


class TestFrameMagnitudeScaleGuardQuarterly:
    def test_dyai_rejects_1000x_frame_tagged_quarterly_outlier(self):
        facts = {
            "us-gaap": {"RevenueFromContractWithCustomerExcludingAssessedTax": _concept(_DYAI_REVENUE_ENTRIES)},
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "DYAI", period="quarterly")

        matching = [
            r
            for r in rows
            if r.get("revenue_from_contract_with_customer_excluding_assessed_tax") in (460_520, 460_520_000)
        ]
        assert matching, f"expected a row for the 2021-01-01..2021-03-31 period, got {rows!r}"
        assert all(r["revenue_from_contract_with_customer_excluding_assessed_tax"] == 460_520 for r in matching), (
            f"Expected DYAI's real Q1 2021 revenue $460,520, got "
            f"{[r['revenue_from_contract_with_customer_excluding_assessed_tax'] for r in matching]!r} - a "
            f"value of $460,520,000 means the quarterly frame-magnitude-scale-guard regression is back"
        )

    def test_genuine_frame_correction_without_round_power_of_ten_ratio_still_wins(self):
        """A REAL restatement (non-power-of-10 divergence) must still win via the pre-existing
        filed-date tiebreak - the new guard must not become a blanket "reject any frame'd
        quarterly-fact change"."""
        facts = {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": _concept(
                    [
                        {
                            "start": "2021-01-01",
                            "end": "2021-03-31",
                            "val": 460_520,
                            "accn": "0001437749-21-012046",
                            "fy": 2021,
                            "fp": "Q1",
                            "form": "10-Q",
                            "filed": "2021-05-13",
                        },
                        {
                            "start": "2021-01-01",
                            "end": "2021-03-31",
                            "val": 483_546,  # real ~5% restatement, not a power-of-10 error
                            "accn": "0001437749-22-012148",
                            "fy": 2022,
                            "fp": "Q1",
                            "form": "10-Q",
                            "filed": "2022-05-12",
                            "frame": "CY2021Q1",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "DYAI", period="quarterly")
        matching = [r for r in rows if r.get("revenue_from_contract_with_customer_excluding_assessed_tax") is not None]
        assert any(r["revenue_from_contract_with_customer_excluding_assessed_tax"] == 483_546 for r in matching)
