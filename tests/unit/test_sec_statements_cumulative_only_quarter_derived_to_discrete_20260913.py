"""Regression test for utils/external/sec_statements_cumulative_quarter_derivation.py.

Live-confirmed 2026-09-13 (goal: keep finding data-quality issues) via RITM's (Fortress
Transportation, real CIK 0001556593) real SEC companyfacts JSON: RITM never files a genuine
discrete-quarter fact for AllocatedShareBasedCompensationExpense at all, so before this fix,
the raw fiscal-year-to-date cumulative fact was stored as-is under Q2/Q3 -
quarterly_cash_flow.stock_based_compensation for 2018 Q2/Q3 both stored 1,019,000 (the H1 and
9mo cumulative totals), not the true ~599,000/0 discrete amounts. This corrupted downstream Q4
derivation too (FY_total - stored_Q1/Q2/Q3, see loaders/helpers/financial_statements_q4_sweeps.
py), since that subtraction assumes Q1-Q3 are already discrete.

Real numbers (AllocatedShareBasedCompensationExpense, fy=2018):
  - Q1: start=2018-01-01 end=2018-03-31 val=420,000 (cumulative == discrete for Q1, always)
  - Q2: start=2018-01-01 end=2018-06-30 val=1,019,000 (H1 cumulative, no discrete fact ever
    filed) -> true discrete Q2 = 1,019,000 - 420,000 = 599,000
  - Q3: start=2018-01-01 end=2018-09-30 val=1,019,000 (9mo cumulative, identical to Q2's
    cumulative - a real zero-incremental-spend quarter, not a bug in the source data) -> true
    discrete Q3 = 1,019,000 - 1,019,000 = 0
"""

from utils.external.sec_statements import get_cash_flow


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0001556593"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


class TestCumulativeOnlyQuarterDerivedToDiscrete:
    def test_ritm_sbc_cumulative_only_quarters_derived_to_discrete(self):
        facts = {
            "us-gaap": {
                "AllocatedShareBasedCompensationExpense": _concept(
                    [
                        {
                            "start": "2018-01-01",
                            "end": "2018-03-31",
                            "val": 420_000,
                            "filed": "2018-05-01",
                            "fp": "Q1",
                            "fy": 2018,
                            "form": "10-Q",
                            "accn": "0001556593-18-000012",
                        },
                        {
                            "start": "2018-01-01",
                            "end": "2018-06-30",
                            "val": 1_019_000,
                            "filed": "2018-07-30",
                            "fp": "Q2",
                            "fy": 2018,
                            "form": "10-Q",
                            "accn": "0001556593-18-000016",
                        },
                        {
                            "start": "2018-01-01",
                            "end": "2018-09-30",
                            "val": 1_019_000,
                            "filed": "2018-10-30",
                            "fp": "Q3",
                            "fy": 2018,
                            "form": "10-Q",
                            "accn": "0001556593-18-000022",
                        },
                        {
                            "start": "2018-01-01",
                            "end": "2018-12-31",
                            "val": 1_020_000,
                            "filed": "2019-02-19",
                            "fp": "FY",
                            "fy": 2018,
                            "form": "10-K",
                            "accn": "0001556593-19-000006",
                        },
                    ]
                ),
                "NetCashProvidedByUsedInOperatingActivities": _concept([]),
                "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations": _concept([]),
                "NetCashProvidedByUsedInInvestingActivities": _concept([]),
                "NetCashProvidedByUsedInFinancingActivities": _concept([]),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_cash_flow(client, "RITM", period="quarterly")
        by_quarter = {r["fiscal_period"]: r for r in rows if r["fiscal_year"] == 2018}

        assert by_quarter["Q1"]["allocated_share_based_compensation_expense"] == 420_000
        assert by_quarter["Q2"]["allocated_share_based_compensation_expense"] == 599_000
        assert by_quarter["Q3"]["allocated_share_based_compensation_expense"] == 0

    def test_genuine_discrete_quarter_is_left_untouched(self):
        """When a real ~90-day discrete fact exists (no cumulative-only bucket), the
        derivation must be a no-op - a normal filer's revenue is unaffected."""
        facts = {
            "us-gaap": {
                "AllocatedShareBasedCompensationExpense": _concept(
                    [
                        {
                            "start": "2018-01-01",
                            "end": "2018-03-31",
                            "val": 100_000,
                            "filed": "2018-05-01",
                            "fp": "Q1",
                            "fy": 2018,
                            "form": "10-Q",
                        },
                        {
                            "start": "2018-04-01",
                            "end": "2018-06-30",
                            "val": 150_000,
                            "filed": "2018-07-30",
                            "fp": "Q2",
                            "fy": 2018,
                            "form": "10-Q",
                        },
                    ]
                ),
                "NetCashProvidedByUsedInOperatingActivities": _concept([]),
                "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations": _concept([]),
                "NetCashProvidedByUsedInInvestingActivities": _concept([]),
                "NetCashProvidedByUsedInFinancingActivities": _concept([]),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_cash_flow(client, "RITM", period="quarterly")
        by_quarter = {r["fiscal_period"]: r for r in rows if r["fiscal_year"] == 2018}

        assert by_quarter["Q1"]["allocated_share_based_compensation_expense"] == 100_000
        assert by_quarter["Q2"]["allocated_share_based_compensation_expense"] == 150_000
