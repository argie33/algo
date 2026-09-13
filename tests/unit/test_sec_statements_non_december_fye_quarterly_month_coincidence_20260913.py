"""Regression test for a fiscal-year-end misdetection bug in
_aggregate_concepts_build_unit_context (utils/external/sec_statements_unit_context.py):

An income-statement/cash-flow concept (Revenues, NetIncomeLoss, ...) is always a duration
fact, so the instant-fact fiscal-year-end detector can never fire for it - non-December
fiscal-year filers' income-statement concepts had no direct signal and fell through to a
quarterly self-consistency guess (does a genuine quarterly fact's own fp agree with the
calendar-quarter its end-date month implies under a December fiscal year?). That guess is
unreliable for ANY fiscal year end that is an exact multiple of 3 months offset from December
(March/June/September FYEs, not just December) - their own quarter-end months are drawn from
the identical {03, 06, 09, 12} set the guess checks for, so a genuine, promptly-filed quarterly
fact can coincidentally satisfy the December mapping purely by chance.

Live-confirmed via UHAL (U-Haul Holding Company/AMERCO, real fiscal year end March 31): its own
"Revenues" concept already carries real FY-tagged duration facts (every one, 2010-2026, ending
March 31) directly showing a March fiscal year end, but a genuine, promptly-filed fp="Q3"
fact (end=2024-09-30, filed 37 days later - UHAL's real fiscal Q3) coincidentally satisfied the
December-fiscal-year quarterly self-consistency guess, flipping has_december_fiscal_year_end to
True. That then triggered the AMZN-rolling-window guard (a non-December-fiscal-year filer's
annual total must end in December, or it's rejected as a rolling window) to reject every one of
UHAL's real "Revenues" facts (all end in March), leaving "revenue" to fall back to a much
smaller ASC-606 sub-line concept (RevenueFromContractWithCustomerExcludingAssessedTax, ~$699M
vs the real ~$5.7B for FY2022) - feeding UHAL into the quarterly_revenue_sum_vs_annual_extreme
DataPatrol quarantine.

Fix: a genuine FY-tagged duration fact directly reveals this concept's real fiscal-year-end
month - far more authoritative than the quarterly guess - but only when EVERY FY-tagged
duration fact in the concept's history unanimously agrees on the same end month (a 52/53-week
fiscal calendar, e.g. SWK/Stanley Black & Decker, legitimately drifts between December and
early January some years - see test_sec_statements_fiscal_year_end_crosses_january.py, which
must stay unaffected).
"""

from utils.external.sec_statements import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000004457"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


class TestNonDecemberFyeQuarterlyMonthCoincidence:
    def test_march_fye_revenue_not_rejected_by_coincidental_quarterly_match(self):
        facts = {
            "us-gaap": {
                "Revenues": _concept(
                    [
                        {
                            "start": "2020-04-01",
                            "end": "2021-03-31",
                            "val": 4_541_985_000.0,
                            "filed": "2021-05-26",
                            "fp": "FY",
                            "fy": 2021,
                            "form": "10-K",
                        },
                        {
                            "start": "2021-04-01",
                            "end": "2022-03-31",
                            "val": 5_739_747_000.0,
                            "filed": "2022-05-25",
                            "fp": "FY",
                            "fy": 2022,
                            "form": "10-K",
                        },
                        # UHAL's own real fiscal Q3 fact - a genuine, promptly-filed single
                        # quarter (91 days, filed 37 days after end) whose end month (09)
                        # coincidentally satisfies the December-fiscal-year quarterly
                        # self-consistency guess's Q3->09 mapping, despite UHAL's real FYE
                        # being March.
                        {
                            "start": "2024-07-01",
                            "end": "2024-09-30",
                            "val": 1_658_108_000.0,
                            "filed": "2024-11-06",
                            "fp": "Q3",
                            "fy": 2024,
                            "form": "10-Q",
                        },
                    ]
                ),
                "RevenueFromContractWithCustomerExcludingAssessedTax": _concept(
                    [
                        {
                            "start": "2021-04-01",
                            "end": "2022-03-31",
                            "val": 699_386_000.0,
                            "filed": "2024-05-30",
                            "fp": "FY",
                            "fy": 2024,
                            "form": "10-K",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "UHAL", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2022]["revenues"] == 5_739_747_000.0
        assert by_year[2022]["revenue_from_contract_with_customer_excluding_assessed_tax"] == 699_386_000.0
