"""Regression test: GROW (US Global Investors, a small investment adviser) has no
"Revenues"/"SalesRevenueNet"/ASC-606 concept at all for FY2013-2017 - its only real revenue
tag those years is "InvestmentAdvisoryManagementAndAdministrativeFees" (live-confirmed via
real SEC companyfacts JSON: $17.318M FY2013, $11.439M/$8.534M FY2014, $9.371M/$7.333M
FY2015, down to $6.763M FY2017 - a real, plausible declining-AUM trajectory).

Before this fix, this concept was never mapped anywhere, so a tiny, unrelated
"InvestmentIncomeInterestAndDividend" fact (e.g. $188,000 for FY2013) won "revenue" by
default, tripping quarterly_revenue_sum_vs_annual_extreme (real quarterly revenue summing
to >10x the bogus annual figure). Same missing-concept-mapping bug class as ARCB/MGPI/ETR,
just without "revenue"/"sales" in the concept's own name - see
[[quarantine_backlog_empirical_verification_20260913]] in memory.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from utils.external.sec_statements import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0001238044"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _entry(start: str, end: str, val: float, filed: str, fp: str = "FY", fy: int = 2013) -> dict:
    return {"start": start, "end": end, "val": val, "filed": filed, "fp": fp, "fy": fy, "form": "10-K"}


def test_grow_investment_advisory_fees_recovered_when_no_revenues_concept_exists():
    facts = {
        "us-gaap": {
            "InvestmentAdvisoryManagementAndAdministrativeFees": {
                "units": {
                    "USD": [
                        _entry("2012-07-01", "2013-06-30", 17_318_000.0, "2013-09-13", fy=2013),
                    ]
                }
            },
            "InvestmentIncomeInterestAndDividend": {
                "units": {
                    "USD": [
                        _entry("2012-07-01", "2013-06-30", 188_000.0, "2013-09-13", fy=2013),
                    ]
                }
            },
        },
        "ifrs-full": {},
    }
    client = _FakeClient(facts)

    rows = get_income_statement(client, "GROW", period="annual")
    by_year = {r["fiscal_year"]: r for r in rows}

    assert by_year[2013]["investment_advisory_management_and_administrative_fees"] == 17_318_000.0


def test_field_mapping_routes_investment_advisory_concept_to_revenue_column():
    loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
    loader.table_name = "annual_income_statement"
    loader.period = "annual"
    loader.statement_type = "income"
    loader._schema_cols = frozenset({"symbol", "fiscal_year", "revenue", "data_unavailable", "reason"})
    loader._field_mapping = {
        "investment_advisory_management_and_administrative_fees": "revenue",
        "data_unavailable": "data_unavailable",
        "reason": "reason",
    }
    loader._fallback_only_fields = frozenset()

    row = {
        "symbol": "GROW",
        "fiscal_year": 2013,
        "investment_advisory_management_and_administrative_fees": 17_318_000.0,
    }

    transformed = loader.transform([row])

    assert transformed[0]["revenue"] == 17_318_000.0
