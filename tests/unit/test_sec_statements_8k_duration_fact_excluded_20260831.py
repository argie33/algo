"""Regression test for a cross-company data-corruption bug in _aggregate_concepts()
(utils/external/sec_statements.py), found during the 2026-08-31 goal session ("get all the
data we need" full-coverage audit) while backfilling a real fix for a different symbol.

Live-confirmed via real SEC companyfacts JSON: Essential Utilities (WTRG, CIK 0000078128)
tags RevenueFromContractWithCustomerExcludingAssessedTax for FY2023/2024/2025 under a
single 2026-03-25 "Regulation FD Disclosure" 8-K (accn 0001193125-26-124163, fp=None,
fy=None) with values ($4.217B/$4.653B/$5.121B) that exactly match American Water Works'
(AWK, an unrelated company) real 10-K-sourced revenue for the same years to the dollar -
not WTRG's own real revenue (WTRG's genuine "Revenues" concept for the same years, sourced
from real 10-Ks, is ~$2.1-2.5B). Because RevenueFromContractWithCustomerExcludingAssessedTax
is listed after "Revenues" in get_income_statement()'s concepts list (ASC-606 tags
legitimately supersede the older concept for most post-2018 filers), this bad 8-K value
silently overwrote WTRG's real revenue in annual_income_statement, corrupting every
downstream ratio (net_margin, gross_margin, etc.) with no data_unavailable/reason flag
anywhere.

Fix: duration facts (has "start") sourced from an 8-K are never accepted into the annual/
quarterly aggregation, regardless of span/fp - Item 9.01 exhibits, investor-presentation
Regulation FD disclosures, and other 8-K content are not subject to the same XBRL-tagging
rigor as a 10-K/10-Q and can carry numbers that are wrong or belong to someone else
entirely. This does NOT extend to DEF 14A/proxy statements - the 2026-07-31 fix for
quarterly-only reporters (ETFs like EE with no full annual filing) deliberately relies on
accepting fp=None duration data from those, and is unaffected by this fix.
"""

from utils.external.sec_statements import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000078128"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


class TestEightKDurationFactExcluded:
    def test_8k_sourced_revenue_does_not_overwrite_real_10k_revenue(self):
        facts = {
            "us-gaap": {
                "Revenues": _concept(
                    [
                        {
                            "start": "2025-01-01",
                            "end": "2025-12-31",
                            "val": 2_474_615_000,
                            "filed": "2026-02-20",
                            "fp": "FY",
                            "fy": 2025,
                            "form": "10-K",
                        },
                    ]
                ),
                "RevenueFromContractWithCustomerExcludingAssessedTax": _concept(
                    [
                        {
                            "start": "2025-01-01",
                            "end": "2025-12-31",
                            "val": 5_121_000_000,  # AWK's real revenue, wrongly tagged under WTRG's CIK
                            "filed": "2026-03-25",
                            "fp": None,
                            "fy": None,
                            "form": "8-K",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "WTRG", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["revenues"] == 2_474_615_000
        assert "revenue_from_contract_with_customer_excluding_assessed_tax" not in by_year[2025]

    def test_def_14a_proxy_revenue_still_accepted_when_no_better_source(self):
        """Guard against over-fixing: the 2026-07-31 fp=None proxy-statement fallback for
        quarterly-only reporters (no full annual filing) must be unaffected - only 8-K is
        excluded, not every non-10-K form."""
        facts = {
            "us-gaap": {
                "Revenues": _concept(
                    [
                        {
                            "start": "2025-01-01",
                            "end": "2025-12-31",
                            "val": 42_000_000,
                            "filed": "2026-04-01",
                            "fp": None,
                            "fy": None,
                            "form": "DEF 14A",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "EE", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["revenues"] == 42_000_000
