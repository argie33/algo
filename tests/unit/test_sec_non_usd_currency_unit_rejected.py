"""Regression test for a currency-unit bug in _aggregate_concepts()
(utils/external/sec_statements.py):

Foreign private issuers filing 20-F/40-F often report monetary XBRL facts in home-market
currency instead of USD, with no separate USD-denominated fact anywhere in the filing.
_aggregate_concepts used to loop over every unit key under a concept's "units" dict
(`for _unit, entries in units.items()`) with no filter, so these filers' raw local-currency
magnitudes were written into USD-denominated DB columns unchanged - live-confirmed via real
companyfacts JSON: SHG (Shinhan Financial Group) tags "Assets" only under unit="KRW"
(739.76e12 raw KRW - real total assets are ~$550B USD, off by ~1350x, the KRW/USD rate),
MUFG/SMFG only under unit="JPY". A live DB scan found 15 symbols with total_assets > $50
trillion, all real foreign banks/industrials whose true USD-equivalent figures are 2-4 orders
of magnitude smaller.

Fix: skip any unit that looks like a 3-letter uppercase ISO-4217 currency code other than
"USD" - no reliable per-filer FX rate exists in XBRL to convert these correctly, so a filer
left without a real USD fact gets an honest NULL instead of a silently wrong number. "shares"/
"pure"/"USD/shares" units (share counts, ratios, per-share figures) don't match this 3-letter
shape and are unaffected.
"""

from typing import Any

from utils.external.sec_statements import get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000000000"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(year: int, val: float, filed: str, form: str = "20-F") -> dict[str, Any]:
    return {"end": f"{year}-12-31", "val": val, "filed": filed, "fp": "FY", "fy": year, "form": form}


class TestNonUsdCurrencyUnitRejected:
    def test_krw_only_assets_produces_no_fabricated_row(self) -> None:
        facts = {
            "us-gaap": {
                "Assets": {"units": {"KRW": [_entry(2024, 739_764_256_000_000.0, "2025-03-01")]}},
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "SHG", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        # The bug: this used to be the raw KRW magnitude (739.76 trillion) masquerading as USD.
        assert 2024 not in by_year or "assets" not in by_year[2024]

    def test_usd_fact_still_accepted_alongside_a_rejected_foreign_currency_fact(self) -> None:
        facts = {
            "us-gaap": {
                "Assets": {
                    "units": {
                        "USD": [_entry(2010, 219_060_641_000.0, "2011-03-01", form="20-F")],
                        "KRW": [_entry(2024, 739_764_256_000_000.0, "2025-03-01")],
                    }
                },
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "SHG", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2010]["assets"] == 219_060_641_000.0
        assert 2024 not in by_year or "assets" not in by_year[2024]

    def test_share_count_and_pure_units_unaffected(self) -> None:
        # "shares" and "pure" don't match the 3-letter-uppercase-currency-code shape and
        # must still pass through normally.
        facts = {
            "us-gaap": {
                "Assets": {"units": {"USD": [_entry(2024, 1_000.0, "2025-03-01", form="10-K")]}},
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "AAPL", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2024]["assets"] == 1_000.0
