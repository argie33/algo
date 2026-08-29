"""Regression test for a quarterly-revenue mis-selection bug in
_aggregate_concepts() (utils/external/sec_statements.py):

Live-verified 2026-08-29 (goal: composite-score validation against real data) via META's real
companyfacts JSON. Every Q2/Q3 10-Q discloses BOTH the discrete "three months ended" duration
fact and the cumulative "six/nine months ended" duration fact for the same revenue concept - SEC
tags fp='Q2'/'Q3' on the FILING's own period for both, so they collide into the identical
(fiscal_year, fp) bucket with the identical filed date (same filing). The old tiebreak fell
through to plain "latest filed wins", which degenerates to "whichever entry iterates first" on an
exact tie - and for META that consistently picked the CUMULATIVE fact.

Real numbers (RevenueFromContractWithCustomerExcludingAssessedTax, fy=2026 fp=Q2):
  - discrete:   start=2026-04-01 end=2026-06-30 val=$60,801,000,000 frame="CY2026Q2"
  - cumulative: start=2026-01-01 end=2026-06-30 val=$117,111,000,000 frame=None
quarterly_income_statement stored the $117.111B H1-cumulative figure as META's "Q2 2026 revenue",
corrupting every downstream growth_metrics YoY/TTM calculation (revenue_growth_1y came out
-71.98% against margins that were actually improving). Same pattern independently confirmed for
AAPL and MSFT - this is systemic across calendar-Q2/Q3 filers, not a META-specific data issue.

Fix: for quarterly duration facts specifically, prefer the entry with the SHORTER start-to-end
span (a genuine single quarter is always ~89-92 days; a same-fiscal-year cumulative echo is
always ~180-190 or ~270-280 days) before falling back to filed-date as a tiebreak.
"""

from utils.external.sec_statements import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0001326801"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


class TestQuarterlyDiscreteVsCumulativeRevenue:
    def test_discrete_quarter_wins_over_ytd_cumulative_same_fp_same_filed_date(self):
        facts = {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": _concept(
                    [
                        {
                            "start": "2026-01-01",
                            "end": "2026-06-30",
                            "val": 117_111_000_000,  # H1 cumulative, no frame
                            "filed": "2026-07-30",
                            "fp": "Q2",
                            "fy": 2026,
                            "form": "10-Q",
                        },
                        {
                            "start": "2026-04-01",
                            "end": "2026-06-30",
                            "val": 60_801_000_000,  # real discrete Q2, frame-tagged
                            "filed": "2026-07-30",
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

        rows = get_income_statement(client, "META", period="quarterly")
        by_year_quarter = {(r["fiscal_year"], r["fiscal_period"]): r for r in rows}

        assert (
            by_year_quarter[(2026, "Q2")]["revenue_from_contract_with_customer_excluding_assessed_tax"]
            == 60_801_000_000
        )

    def test_discrete_quarter_wins_regardless_of_list_order(self):
        """Same facts, reversed order - the fix must not be order-dependent."""
        facts = {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": _concept(
                    [
                        {
                            "start": "2025-07-01",
                            "end": "2025-09-30",
                            "val": 51_242_000_000,  # real discrete Q3
                            "filed": "2025-10-30",
                            "fp": "Q3",
                            "fy": 2025,
                            "form": "10-Q",
                            "frame": "CY2025Q3",
                        },
                        {
                            "start": "2025-01-01",
                            "end": "2025-09-30",
                            "val": 141_073_000_000,  # 9mo cumulative
                            "filed": "2025-10-30",
                            "fp": "Q3",
                            "fy": 2025,
                            "form": "10-Q",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "META", period="quarterly")
        by_year_quarter = {(r["fiscal_year"], r["fiscal_period"]): r for r in rows}

        assert (
            by_year_quarter[(2025, "Q3")]["revenue_from_contract_with_customer_excluding_assessed_tax"]
            == 51_242_000_000
        )

    def test_restated_same_span_still_uses_filed_date_tiebreak(self):
        """Two discrete-quarter facts (same ~90-day span) for the same period - a genuine
        restatement - must still fall back to filed-date, not get stuck comparing equal spans."""
        facts = {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": _concept(
                    [
                        {
                            "start": "2025-04-01",
                            "end": "2025-06-30",
                            "val": 47_500_000_000,
                            "filed": "2025-07-31",
                            "fp": "Q2",
                            "fy": 2025,
                            "form": "10-Q",
                        },
                        {
                            "start": "2025-04-01",
                            "end": "2025-06-30",
                            "val": 47_516_000_000,  # restated, filed later
                            "filed": "2025-08-15",
                            "fp": "Q2",
                            "fy": 2025,
                            "form": "10-Q/A",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "META", period="quarterly")
        by_year_quarter = {(r["fiscal_year"], r["fiscal_period"]): r for r in rows}

        assert (
            by_year_quarter[(2025, "Q2")]["revenue_from_contract_with_customer_excluding_assessed_tax"]
            == 47_516_000_000
        )
