"""Regression test for a currency-tagging bug found during the score-sanity/XBRL audit
(goal session 2026-09-07): _aggregate_concepts() (utils/external/sec_statements_aggregate.py)
already skips any non-USD, non-MAJOR_CURRENCIES unit outright (see
test_sec_non_usd_currency_unit_rejected.py), but never cross-checked a "USD"-tagged fact
against a same-period, identically-valued fact tagged under one of those rejected currencies.

Live-confirmed via BWMX (Betterware de Mexico, S.A.P.I. de C.V., CIK 0001788257)'s real 20-F
XBRL: ifrs-full:RevenueFromContractsWithCustomers is tagged as BOTH MXN 10,067,683,000 and
USD 10,067,683,000 for the same FY2023 period - a filer-side tagging error (the raw MXN figure
duplicated under a USD unitRef, not a real USD-denominated fact; real FY2023 revenue is
~$500-600M USD at prevailing MXN/USD rates, not $10.07B). Since MXN isn't in MAJOR_CURRENCIES,
the MXN-tagged fact was correctly rejected, but the identically-valued "USD" sibling sailed
through untouched, inflating value_metrics' ps_ratio/ev_revenue by roughly the full MXN/USD
rate (~18-20x) for this filer. The same duplicate-value pattern also appeared on
ifrs-full:ProfitLossAttributableToOwnersOfParent (MXN 298,444,000/1,751,645,000 == the
"USD"-tagged FY2022/FY2021 figures too), so this isn't a one-off single-concept fluke for this
filer.

Fix: a "USD" fact is now cross-checked against every rejected (non-major, non-USD) currency
unit for the SAME concept; an exact (start, end, val) match marks it as a spurious duplicate
tag rather than a real independent USD fact, and it is dropped the same way the foreign-
currency original already was.
"""

from typing import Any

from utils.external.sec_statements import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0001788257"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(year: int, val: float, filed: str, form: str = "20-F") -> dict[str, Any]:
    return {
        "start": f"{year - 1}-01-01",
        "end": f"{year}-12-31",
        "val": val,
        "filed": filed,
        "fp": "FY",
        "fy": year,
        "form": form,
    }


class TestSpuriousUsdDuplicateOfLocalCurrencyFactRejected:
    def test_usd_fact_identical_to_rejected_mxn_fact_is_dropped(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "RevenueFromContractsWithCustomers": {
                    "units": {
                        "MXN": [_entry(2023, 10_067_683_000.0, "2024-04-01")],
                        "USD": [_entry(2023, 10_067_683_000.0, "2024-04-01")],
                    }
                },
            },
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "BWMX", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        # The bug: this used to accept the raw MXN magnitude masquerading as USD revenue.
        assert 2023 not in by_year or "revenue_from_contract_with_customer_excluding_assessed_tax" not in by_year[2023]

    def test_real_usd_fact_with_no_matching_foreign_duplicate_is_still_accepted(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "RevenueFromContractsWithCustomers": {
                    "units": {
                        "MXN": [_entry(2022, 7_237_628_000.0, "2023-04-01")],
                        "USD": [_entry(2023, 500_000_000.0, "2024-04-01")],
                    }
                },
            },
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "BWMX", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        # Different year AND different value from the rejected MXN fact - a real,
        # independent USD figure, must not be caught by the duplicate-tag guard.
        assert by_year[2023]["revenue_from_contract_with_customer_excluding_assessed_tax"] == 500_000_000.0
        assert 2022 not in by_year or "revenue_from_contract_with_customer_excluding_assessed_tax" not in by_year[2022]
