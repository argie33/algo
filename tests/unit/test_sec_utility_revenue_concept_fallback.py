"""Regression test: regulated electric/gas utilities (XEL/Xcel Energy, DTE/DTE Energy,
OGS/ONE Gas live-confirmed via real SEC companyfacts JSON) switched their primary revenue
tag to "RegulatedAndUnregulatedOperatingRevenue" around FY2018/2019 (ASC 606 adoption
era) - "Revenues"/"RevenueFromContractWithCustomerExcludingAssessedTax" both stop updating
for these filers even though the company keeps filing real 10-Ks every year after.

Before this fix, `annual_income_statement.revenue` was NULL for 7+ straight years despite
real net_income/operating_income continuing to populate every year - and because
load_value_quality_growth_metrics.py's quality_row query ranks any fiscal year with a real
`revenue` value above one without it (regardless of recency), this silently froze the
symbol's ENTIRE quality_metrics/growth_metrics row behind a multi-year-stale anchor,
tripping the stale_fiscal_data gate for a company that in fact files every year. Same bug
class as the AEG/UBS IFRS revenue-relabeling fixes, different (ASC-606/utility-sector)
trigger.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from utils.external.sec_statements import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000072903"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _entry(start: str, end: str, val: float, filed: str, fp: str = "FY", fy: int = 2025) -> dict:
    return {"start": start, "end": end, "val": val, "filed": filed, "fp": fp, "fy": fy, "form": "10-K"}


def test_regulated_utility_revenue_recovered_after_legacy_concept_goes_silent():
    facts = {
        "us-gaap": {
            "Revenues": {
                "units": {
                    "USD": [
                        _entry("2018-01-01", "2018-12-31", 11_537_000_000.0, "2019-02-15", fy=2018),
                    ]
                }
            },
            "RegulatedAndUnregulatedOperatingRevenue": {
                "units": {
                    "USD": [
                        # Overlap year: matches the legacy "Revenues" tag exactly.
                        _entry("2018-01-01", "2018-12-31", 11_537_000_000.0, "2019-02-15", fy=2018),
                        # "Revenues" goes silent after 2018, but the company keeps filing
                        # real 10-Ks with this concept for years after.
                        _entry("2025-01-01", "2025-12-31", 14_669_000_000.0, "2026-02-20", fy=2025),
                    ]
                }
            },
        },
        "ifrs-full": {},
    }
    client = _FakeClient(facts)

    rows = get_income_statement(client, "XEL", period="annual")
    by_year = {r["fiscal_year"]: r for r in rows}

    assert by_year[2018]["regulated_and_unregulated_operating_revenue"] == 11_537_000_000.0
    assert by_year[2025]["regulated_and_unregulated_operating_revenue"] == 14_669_000_000.0


def test_field_mapping_routes_utility_concept_to_revenue_column():
    loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
    loader.table_name = "annual_income_statement"
    loader.period = "annual"
    loader.statement_type = "income"
    loader._schema_cols = frozenset({"symbol", "fiscal_year", "revenue", "data_unavailable", "reason"})
    loader._field_mapping = {
        "regulated_and_unregulated_operating_revenue": "revenue",
        "data_unavailable": "data_unavailable",
        "reason": "reason",
    }
    loader._fallback_only_fields = frozenset()

    row = {
        "symbol": "XEL",
        "fiscal_year": 2025,
        "regulated_and_unregulated_operating_revenue": 14_669_000_000.0,
    }

    transformed = loader.transform([row])

    assert transformed[0]["revenue"] == 14_669_000_000.0
