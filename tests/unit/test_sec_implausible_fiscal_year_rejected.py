"""Regression test for a fiscal-year sanity-bound bug in _aggregate_concepts()
(utils/external/sec_statements.py):

SEC's own XBRL data is occasionally corrupted in ways that produce an implausible fiscal
year from either derivation path (end-date year, or the trusted "fy" field). Two distinct
patterns live-confirmed against SEC's real API:

1. NAII (Natural Alternatives International): a NetIncomeLoss fact tagged
   end="2031-09-25" (evidently meant 2023 - real net_income data, fy=2022 on the very
   same fact is plausible) fed fiscal_year=2031 via the end-date derivation - writing
   REAL revenue/net_income into the DB under a 5-years-in-the-future fiscal year
   (data_unavailable=False, so any "ORDER BY fiscal_year DESC LIMIT 1" caller would pick
   this up as the "latest" data).

2. PRTH (Priority Technology Holdings): dei:EntityCommonStockSharesOutstanding facts
   carry fy=43465/43830 directly in SEC's own JSON - an Excel-serial-like value, not a
   real year - which the DEI-source branch previously trusted verbatim. This also broke
   data_loader_status's MAX(fiscal_year) -> date(fiscal_year, 12, 31) watermark write
   every run ("year 43830 is out of range", live-confirmed in
   logs/load_financial_statements_1787150329.log).

Neither end_date nor fy is trustworthy in isolation, so the fix falls back to whichever
of the two is itself plausible (bounded to [1990, this_year + 1]), and skips the entry
entirely - rather than writing garbage - only if neither is.
"""

import datetime

from utils.external.sec_statements import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict):
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000787253"

    def get_company_facts(self, cik: str) -> dict:
        return {"facts": self._facts}


def _concept(entries: list[dict]) -> dict:
    return {"units": {"USD": entries}}


def _shares_concept(entries: list[dict]) -> dict:
    return {"units": {"shares": entries}}


class TestImplausibleFiscalYearRejected:
    def test_corrupted_end_date_falls_back_to_plausible_fy(self) -> None:
        """NAII case: end-date year (2031) is implausible, entry's own fy (2022) is
        plausible - the plausible fy must win rather than corrupting the DB with a
        5-years-in-the-future fiscal year for real financial data."""
        facts = {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": _concept(
                    [
                        {
                            "start": "2023-01-01",
                            "end": "2031-09-25",  # corrupted - real filing meant 2023
                            "val": 32_699_000.0,
                            "filed": "2023-05-15",
                            "fp": "FY",
                            "fy": 2022,
                            "form": "10-K",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
            "dei": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "NAII", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert 2031 not in by_year
        assert by_year[2022]["revenue_from_contract_with_customer_excluding_assessed_tax"] == 32_699_000.0

    def test_corrupted_dei_fy_falls_back_to_plausible_end_date(self) -> None:
        """PRTH case: SEC's own dei fy field (43830) is an Excel-serial-like garbage
        value, but the fact's own end date (2020-03-26) is plausible - the plausible
        end-date year must win rather than writing fiscal_year=43830 into the DB (which
        also crashes date(fiscal_year, 12, 31) in the watermark/status update)."""
        facts = {
            "us-gaap": {"Assets": _concept([])},
            "ifrs-full": {},
            "dei": {
                "EntityCommonStockSharesOutstanding": _shares_concept(
                    [
                        {
                            "end": "2020-03-26",
                            "val": 67_060_943,
                            "filed": "2020-03-30",
                            "fp": "FY",
                            "fy": 43830,  # corrupted - real SEC data, not our bug
                            "form": "10-K",
                        },
                    ]
                ),
            },
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "PRTH", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert 43830 not in by_year
        assert by_year[2020]["entity_common_stock_shares_outstanding"] == 67_060_943

    def test_both_end_date_and_fy_implausible_entry_skipped(self) -> None:
        """When neither derivation is plausible, the entry must be dropped rather than
        writing any garbage fiscal_year into the DB."""
        facts = {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": _concept(
                    [
                        {
                            "start": "2023-01-01",
                            "end": "2031-09-25",  # implausible
                            "val": 32_699_000.0,
                            "filed": "2023-05-15",
                            "fp": "FY",
                            "fy": 43830,  # also implausible
                            "form": "10-K",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
            "dei": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "TEST", period="annual")

        assert rows == []

    def test_near_future_fiscal_year_still_accepted(self) -> None:
        """Sanity check the bound isn't so tight it rejects legitimate near-term data -
        this_year + 1 must still be accepted."""
        next_year = datetime.date.today().year + 1
        facts = {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": _concept(
                    [
                        {
                            "start": f"{next_year}-01-01",
                            "end": f"{next_year}-12-31",
                            "val": 1_000_000.0,
                            "filed": f"{next_year + 1}-02-01",
                            "fp": "FY",
                            "fy": next_year,
                            "form": "10-K",
                        },
                    ]
                ),
            },
            "ifrs-full": {},
            "dei": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "FUT", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert next_year in by_year
