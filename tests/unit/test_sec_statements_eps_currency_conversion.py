"""Regression test: EPS/per-share XBRL facts must go through the same currency
reject-or-convert logic as monetary facts in utils/external/sec_statements.py.

Found live 2026-08-18, follow-up to [[currency_guard_major_currency_conversion_fix_20260817]]
(commit 162fdddfc): that fix taught _aggregate_concepts()'s currency guard to convert
CAD/GBP/EUR/AUD/CHF/JPY monetary facts to USD via a real historical FX rate instead of
rejecting them outright. But BasicEarningsLossPerShare/DilutedEarningsLossPerShare use a
compound unit ("CAD/shares"), not a bare "CAD" - the guard only ever matched bare 3-letter
units, so a CAD filer's EPS silently passed through BOTH un-rejected AND un-converted,
still in raw CAD, while revenue/net_income for the same row now correctly convert and the
row reads data_unavailable=False (i.e. "trust this data"). Worse than the pre-conversion
state, where the whole row was honestly marked unavailable. Same gap would also let a
non-major foreign currency's EPS (e.g. "KRW/shares") through unconverted and un-rejected,
reintroducing the original magnitude-mismatch bug for one column.

Fix: _extract_currency_code() splits the unit on "/" first, so "CAD/shares" -> "CAD" (same
reject-or-convert rule as a bare "CAD" monetary fact) while "shares"/"pure"/"USD/shares"
still correctly fall outside the 3-letter-uppercase-code shape and pass through unaffected.
"""

from typing import Any

from utils.external.sec_statements import _extract_currency_code, get_income_statement


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000000000"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(year: int, val: float, filed: str, form: str = "10-K") -> dict[str, Any]:
    return {"end": f"{year}-12-31", "val": val, "filed": filed, "fp": "FY", "fy": year, "form": form}


class TestExtractCurrencyCode:
    def test_bare_currency_unchanged(self) -> None:
        assert _extract_currency_code("CAD") == "CAD"
        assert _extract_currency_code("USD") == "USD"

    def test_compound_per_share_unit_splits_to_bare_code(self) -> None:
        assert _extract_currency_code("CAD/shares") == "CAD"
        assert _extract_currency_code("USD/shares") == "USD"
        assert _extract_currency_code("KRW/shares") == "KRW"

    def test_non_currency_units_unaffected(self) -> None:
        assert _extract_currency_code("shares") == "shares"
        assert _extract_currency_code("pure") == "pure"


class TestEpsCurrencyConversion:
    def test_major_currency_eps_converted_to_usd(self, monkeypatch) -> None:
        from utils.external import sec_statements

        monkeypatch.setattr(
            sec_statements._fx_rate_cache, "get_usd_rate", lambda code, date: 1.386 if code == "CAD" else None
        )

        facts = {
            "us-gaap": {
                "EarningsPerShareBasic": {"units": {"CAD/shares": [_entry(2025, 4.52, "2026-02-15")]}},
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "CP", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        # Pre-fix: this silently stayed 4.52 (raw CAD) instead of converting.
        assert by_year[2025]["earnings_per_share_basic"] == 4.52 / 1.386

    def test_non_major_currency_eps_rejected_not_passed_through_raw(self) -> None:
        # CLP: still outright rejected (Frankfurter doesn't cover it at all). KRW moved
        # onto MAJOR_CURRENCIES 2026-08-18 - see test_krw_eps_converted_to_usd below and
        # fx_rates.py's docstring for the live-verification behind that move.
        facts = {
            "us-gaap": {
                "EarningsPerShareBasic": {"units": {"CLP/shares": [_entry(2025, 15000.0, "2026-02-15")]}},
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "BCH", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        # Pre-fix: this silently stored the raw CLP magnitude as if USD.
        assert 2025 not in by_year or "earnings_per_share_basic" not in by_year[2025]

    def test_krw_eps_converted_to_usd(self, monkeypatch) -> None:
        # FIX 2026-08-18: KRW moved onto MAJOR_CURRENCIES (real historical-rate
        # conversion) as a follow-up to the currency-poisoning cleanup - see
        # fx_rates.py's docstring for the live-verification (KEP/KB/SHG) behind this.
        from utils.external import sec_statements

        monkeypatch.setattr(
            sec_statements._fx_rate_cache, "get_usd_rate", lambda code, date: 0.00077 if code == "KRW" else None
        )

        facts = {
            "us-gaap": {
                "EarningsPerShareBasic": {"units": {"KRW/shares": [_entry(2025, 15000.0, "2026-02-15")]}},
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "SHG", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["earnings_per_share_basic"] == 15000.0 / 0.00077

    def test_usd_per_share_unaffected(self) -> None:
        facts = {
            "us-gaap": {
                "EarningsPerShareBasic": {"units": {"USD/shares": [_entry(2025, 6.10, "2026-02-15")]}},
            },
            "ifrs-full": {},
        }
        client = _FakeClient(facts)

        rows = get_income_statement(client, "AAPL", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["earnings_per_share_basic"] == 6.10
