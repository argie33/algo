"""Regression test for a duration-fact variant of the comparative-aliasing bug class in
_aggregate_concepts() (utils/external/sec_statements.py), found during the 2026-08-31
goal session ("real-money-readiness" audit) while chasing the CHTR/HTLD/ANDE ASC-606
revenue-clobber fix. See memory jakk_duration_fact_comparative_aliasing_found_not_fixed_20260831
for the original diagnosis.

Live-confirmed via real SEC companyfacts JSON: JAKK (JAKKS Pacific, CIK 1009829) tags a
duration fact under RevenueFromContractWithCustomerExcludingAssessedTax with FULL-YEAR
dates (start=2025-01-01/end=2025-12-31, filed 2026-05-01, from its Q1 2026 10-Q, accn
0001185185-26-001667) but a value of $113,253,000 - exactly matching that SAME accn's own
correctly-tagged Q1-2025-only comparative fact (start=2025-01-01/end=2025-03-31, same
value). JAKK's real FY2025 revenue is $570,671,000 (from its actual FY2025 10-K, filed
2026-03-02). Because the mistagged fact was filed later than the real 10-K and both are
primary-form filings (10-Q counts as primary), the existing "latest filed wins" annual
duration-fact tiebreak let the wrong, later-filed value silently overwrite the correct
one - no data_unavailable/reason flag anywhere.

Fix: within a single accn, if an annual-span (>=330 day) duration fact's value exactly
matches a genuine short-span (<330 day) duration fact for the SAME concept from the SAME
accn, the long-span fact is treated as that quarter's value wearing borrowed annual dates
and is excluded from annual aggregation entirely. Verified against real AAPL/MSFT/CHTR/
ANDE data (685 combined annual-span duration facts) that this signal produces zero false
positives - a real annual total practically never exactly equals a single quarter's total.
"""

from utils.external.sec_statements import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0001009829"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


class TestDurationFactComparativeAliasing:
    def test_annual_span_fact_matching_sibling_quarter_value_is_rejected(self):
        facts = {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": _concept(
                    [
                        # Real FY2025 10-K - the correct annual figure.
                        {
                            "start": "2025-01-01",
                            "end": "2025-12-31",
                            "val": 570_671_000,
                            "filed": "2026-03-02",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                            "accn": "0001185185-26-000723",
                        },
                        # Same accn's own genuine Q1-2025 comparative (correctly tagged).
                        {
                            "start": "2025-01-01",
                            "end": "2025-03-31",
                            "val": 113_253_000,
                            "filed": "2026-05-01",
                            "fp": "Q1",
                            "fy": 2026,
                            "form": "10-Q",
                            "accn": "0001185185-26-001667",
                            "frame": "CY2025Q1",
                        },
                        # The bug: same accn, SAME value as the Q1 fact above, but tagged
                        # with full-year dates and even carrying frame="CY2025" - must NOT
                        # be accepted as FY2025's real revenue.
                        {
                            "start": "2025-01-01",
                            "end": "2025-12-31",
                            "val": 113_253_000,
                            "filed": "2026-05-01",
                            "fp": "Q1",
                            "fy": 2026,
                            "form": "10-Q",
                            "accn": "0001185185-26-001667",
                            "frame": "CY2025",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "JAKK", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["revenue_from_contract_with_customer_excluding_assessed_tax"] == 570_671_000

    def test_genuine_annual_fact_not_rejected_when_no_matching_short_span_sibling(self):
        """Guard against over-fixing: a real annual fact whose value happens not to match
        any short-span sibling in its own accn (the overwhelming normal case) must be
        completely unaffected."""
        facts = {
            "us-gaap": {
                "Revenues": _concept(
                    [
                        {
                            "start": "2025-01-01",
                            "end": "2025-12-31",
                            "val": 570_671_000,
                            "filed": "2026-03-02",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                            "accn": "0001185185-26-000723",
                        },
                        {
                            "start": "2025-01-01",
                            "end": "2025-03-31",
                            "val": 113_253_000,
                            "filed": "2026-03-02",
                            "fp": "Q1",
                            "fy": 2025,
                            "form": "10-K",
                            "accn": "0001185185-26-000723",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "JAKK", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["revenues"] == 570_671_000

    def test_annual_span_fact_with_no_accn_still_processed(self):
        """Guard against over-fixing: an entry missing 'accn' (should not happen in real
        SEC data, but defensive) must not crash and must not be spuriously rejected."""
        facts = {
            "us-gaap": {
                "Revenues": _concept(
                    [
                        {
                            "start": "2025-01-01",
                            "end": "2025-12-31",
                            "val": 570_671_000,
                            "filed": "2026-03-02",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "JAKK", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["revenues"] == 570_671_000
