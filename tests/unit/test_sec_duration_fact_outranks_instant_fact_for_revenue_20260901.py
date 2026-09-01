"""Regression test for the instant-vs-duration fact-selection bug in `_aggregate_concepts()`
(utils/external/sec_statements.py), fixed in commit 76f76a8c0 ("FIX: instant fact could
silently win over a genuine annual duration fact (LADR)") - see
test_sec_statements_duration_fact_beats_instant_fact_20260831.py for that fix's own LADR
coverage and instant-vs-instant tiebreak sanity check. This file adds the SECOND independent
live confirmation of the same mechanism, found continuing the standing real-money-readiness
/goal audit's revenue-collision scan (cost_of_revenue > revenue*10 fingerprint) after the fix
had already landed.

**SRXH** (SRX Global) FY2024: DB showed revenue=$2,000,000. The winning fact was
`RevenueFromContractWithCustomerExcludingAssessedTax` end=2024-06-01, val=$2,000,000,
frame="CY2024Q2I" (the "I" suffix is SEC's own instant-frame marker) - an instant fact beating
the real annual duration fact (start=2024-01-01/end=2024-12-31, val=$34,975,000) for the same
concept and bucket - structurally identical to LADR's case but a different concept, confirming
the fix generalizes beyond the single symbol it was built against, and specifically exercises
the `frame`-present instant case the LADR test didn't cover.
"""

from utils.external.sec_statements import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0001501756"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


class TestDurationFactOutranksInstantFactForRevenue:
    def test_srxh_real_annual_revenue_wins_over_instant_frame_marked_fact(self):
        facts = {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": _concept(
                    [
                        {
                            "start": "2024-01-01",
                            "end": "2024-12-31",
                            "val": 34_975_000,
                            "filed": "2025-03-15",
                            "fp": "FY",
                            "fy": 2024,
                            "form": "10-K",
                        },
                        {
                            # Instant fact (no "start"), SEC's own "I" instant-frame suffix.
                            "end": "2024-06-01",
                            "val": 2_000_000,
                            "filed": "2025-03-15",
                            "fp": "FY",
                            "fy": 2024,
                            "form": "10-K",
                            "frame": "CY2024Q2I",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "SRXH", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2024]["revenue_from_contract_with_customer_excluding_assessed_tax"] == 34_975_000

    def test_instant_fact_still_wins_when_no_duration_fact_present(self):
        """Sanity check: this fix must not reject instant facts outright for concepts that
        are legitimately instant-only (e.g. a filer that only ever tags an instant snapshot
        for some line item) - it only changes the tiebreak when a genuine duration fact
        ALSO exists and collides with it."""
        facts = {
            "us-gaap": {
                "OperatingLeaseLeaseIncome": _concept(
                    [
                        {
                            "end": "2019-05-01",
                            "val": 3_900_000,
                            "filed": "2020-02-27",
                            "fp": "FY",
                            "fy": 2019,
                            "form": "10-K",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "LADR", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2019]["operating_lease_lease_income"] == 3_900_000
