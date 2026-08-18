"""Regression test for the 2026-08-17 IFRS lease-liability alias (loader-review goal
continuation).

Unlike US GAAP's ASC 842 (which splits lessee lease liabilities into separate
OperatingLeaseLiability/FinanceLeaseLiability tags, migration 1205), IFRS 16 gives
lessees a single unified lease-liability model with no operating/finance split. No IFRS
alias existed for either GAAP concept, so every IFRS-only filer (20-F/40-F) got NULL
lease liabilities entirely, understating total_debt for lease-heavy IFRS filers
(retailers, airlines, telecoms).

Live-confirmed via real companyfacts JSON that "LeaseLiabilities" is the filer's own true
Current+Noncurrent total (not a partial/dimensional fact) for RIO (Rio Tinto,
$1.586B == $524M + $1.062M) and BP ($14.571B == $2.832B + $11.739B). Mapped to
"operating_lease_liability" (not a new column) so it flows through the existing
total_debt = long_term_debt + short_term_debt + operating_lease_liability +
finance_lease_liability sum unchanged.
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


class TestIfrsLeaseLiabilityAlias:
    def test_lease_liabilities_maps_to_operating_lease_liability(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "LeaseLiabilities": {"units": {"USD": [_entry(2025, 1_586_000_000.0, "2026-02-20")]}},
            },
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "RIO", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["operating_lease_liability"] == 1_586_000_000.0
        assert "finance_lease_liability" not in by_year[2025]

    def test_non_usd_lease_liabilities_converted_via_major_currency_fx_rate(self, monkeypatch) -> None:
        # EUR is on the MAJOR_CURRENCIES whitelist (utils/external/fx_rates.py, 2026-08-17),
        # so a EUR-denominated filer (e.g. E/Eni) gets a real converted USD figure instead of
        # a fabricated one or a dropped one - see test_sec_non_usd_currency_unit_rejected.py
        # for the still-active reject case (exotic/volatile currencies not on the whitelist).
        import utils.external.sec_statements as sec_statements_mod

        monkeypatch.setattr(sec_statements_mod._fx_rate_cache, "get_usd_rate", lambda currency, date_str: 1.05)

        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "LeaseLiabilities": {"units": {"EUR": [_entry(2025, 5_700_000_000.0, "2026-02-20")]}},
            },
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "E", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["operating_lease_liability"] == 5_700_000_000.0 / 1.05
