"""Regression test for the 2026-08-17 ifrs-full:DividendsPaidClassifiedAsFinancingActivities
alias (user-reported live on the Scores page: AEM's Value tab showed dividend_yield "SEC data
not available" despite AEM being a real, long-time dividend payer).

Root cause: AEM is a 40-F/20-F Canadian foreign private issuer that reports both us-gaap and
ifrs-full facts. Its us-gaap:PaymentsOfDividendsCommonStock data (already aliased) stops at
FY2013 - the filer switched taxonomies - and the existing ifrs-full "DividendsPaid" alias was
never AEM's real concept name. Live-confirmed via real companyfacts JSON: AEM reports
ifrs-full:DividendsPaidClassifiedAsFinancingActivities every fiscal year through FY2025
($728.1M FY2025, $671.7M FY2024) - the actual cash-flow-statement financing-activities
dividend line. AEM ALSO reports a sibling concept, ifrs-full:DividendsPaidOrdinaryShares
($802.9M FY2025) - a different, larger figure (not the cash-flow-statement line) -
deliberately NOT aliased, so this test also guards against ever conflating the two.
"""

from typing import Any

from utils.external.sec_statements import get_cash_flow


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000002809"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(year: int, val: float, filed: str, form: str = "40-F") -> dict[str, Any]:
    return {"end": f"{year}-12-31", "val": val, "filed": filed, "fp": "FY", "fy": year, "form": form}


class TestIfrsDividendsPaidFinancingActivitiesAlias:
    def test_dividends_paid_classified_as_financing_activities_maps_to_payments_of_dividends(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "DividendsPaidClassifiedAsFinancingActivities": {
                    "units": {"USD": [_entry(2025, 728_077_000.0, "2026-02-13")]},
                },
            },
        }
        client = _FakeClient(facts)

        rows = get_cash_flow(client, "AEM", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["payments_of_dividends"] == 728_077_000.0

    def test_sibling_dividends_paid_ordinary_shares_concept_is_not_aliased(self) -> None:
        """DividendsPaidOrdinaryShares is a real, different figure AEM also reports - not
        the cash-flow-statement financing-activities line. Must stay unmapped so a future
        session doesn't casually alias it thinking it's a duplicate/equivalent of the
        concept above."""
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "DividendsPaidOrdinaryShares": {
                    "units": {"USD": [_entry(2025, 802_884_000.0, "2026-02-13")]},
                },
            },
        }
        client = _FakeClient(facts)

        rows = get_cash_flow(client, "AEM", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert 2025 not in by_year or by_year[2025].get("payments_of_dividends") is None

    def test_non_usd_dividends_paid_rejected_by_currency_guard(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "DividendsPaidClassifiedAsFinancingActivities": {
                    "units": {"CAD": [_entry(2025, 1_000_000_000.0, "2026-02-13")]},
                },
            },
        }
        client = _FakeClient(facts)

        rows = get_cash_flow(client, "AEM", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert 2025 not in by_year or by_year[2025].get("payments_of_dividends") is None
