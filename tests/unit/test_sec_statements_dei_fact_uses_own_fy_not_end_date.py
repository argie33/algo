"""Regression test for a fiscal-year phantom-bucket bug in _aggregate_concepts()
(utils/external/sec_statements.py):

DEI cover-page facts (e.g. EntityCommonStockSharesOutstanding) are "as of the latest
practicable date before filing" snapshots, not economic-activity facts - their own end
date can land weeks to months after the real fiscal year end. Live-confirmed against
SEC's real API for AAP (Advance Auto Parts): the FY2024 10-K's real revenue duration
fact ends 2024-12-28 (correctly bucketed fiscal_year=2024, fy=2024), but its
accompanying dei:EntityCommonStockSharesOutstanding cover-page fact is dated
2025-02-19 (fy=2024) - 6 weeks later, crossing into the next calendar year.

Bucketing DEI facts by end-date year (the general rule, justified for us-gaap/ifrs facts
since SEC's fy tag conflates current-year and comparative-year data within one filing)
created a phantom fiscal_year=2025 bucket containing ONLY this one DEI fact, sandwiched
between the real FY2024 and FY2026 annual buckets. Every prior-year lookback in
load_value_quality_growth_metrics.py keys strictly off fiscal_year-1, so this phantom
bucket silently blocked every *_growth_yoy/*_trend metric for the symbol.

Unlike us-gaap/ifrs facts, DEI cover-page facts don't carry historical comparative-year
entries (one "as of" value per filing, not a multi-year table), so entry['fy'] is
trustworthy here - the fix buckets DEI facts by their own fy field instead of end date.
"""

from utils.external.sec_statements import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000913691"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


def _shares_concept(entries: list[dict]) -> dict:
    return {"units": {"shares": entries}}


class TestDeiFactUsesOwnFiscalYear:
    def test_dei_cover_page_fact_merges_into_real_fiscal_year_not_end_date_year(self):
        facts = {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": _concept(
                    [
                        {
                            "start": "2023-12-31",
                            "end": "2024-12-28",
                            "val": 9_094_000_000.0,
                            "filed": "2025-02-26",
                            "fp": "FY",
                            "fy": 2024,
                            "form": "10-K",
                        },
                        {
                            "start": "2024-12-29",
                            "end": "2026-01-03",
                            "val": 8_601_000_000.0,
                            "filed": "2026-02-13",
                            "fp": "FY",
                            "fy": 2026,
                            "form": "10-K",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
            "dei": {
                "EntityCommonStockSharesOutstanding": _shares_concept(
                    [
                        {
                            "end": "2025-02-19",
                            "val": 59_792_946,
                            "filed": "2025-02-26",
                            "fp": "FY",
                            "fy": 2024,
                            "form": "10-K",
                        },
                        {
                            "end": "2026-02-09",
                            "val": 60_100_000,
                            "filed": "2026-02-13",
                            "fp": "FY",
                            "fy": 2026,
                            "form": "10-K",
                        },
                    ]
                ),
            },
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "AAP", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        # This is the bug: previously a phantom fiscal_year=2025 bucket existed,
        # containing only the DEI fact and no revenue - sandwiched between the real
        # FY2024 and FY2026 buckets, silently breaking every prior-year lookback.
        assert 2025 not in by_year

        assert by_year[2024]["revenue_from_contract_with_customer_excluding_assessed_tax"] == 9_094_000_000.0
        assert by_year[2024]["entity_common_stock_shares_outstanding"] == 59_792_946

        assert by_year[2026]["revenue_from_contract_with_customer_excluding_assessed_tax"] == 8_601_000_000.0
        assert by_year[2026]["entity_common_stock_shares_outstanding"] == 60_100_000
