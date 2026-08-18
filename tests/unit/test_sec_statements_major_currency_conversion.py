"""Regression test: revenue/net_income for filers reporting in CAD/GBP/EUR/AUD/CHF/JPY
must be converted to USD, not silently dropped by the non-USD currency guard.

Found live 2026-08-17: sec_statements.py's currency guard (added to block KRW/JPY
filers whose raw local-currency magnitudes were being stored as if USD, off by
~100-1000x) was a blanket rule that ALSO rejected CAD/GBP/EUR/AUD/CHF/JPY - developed-
market currencies within roughly a 2x band of USD, nothing like the original bug's
magnitude mismatch. Live-confirmed via CP (Canadian Pacific Kansas City, reports in
CAD): real revenue/net_income data existed in SEC's companyfacts JSON but was
discarded entirely, leaving the row marked data_unavailable='incomplete_sec_filing_income'
despite complete real data being available. 272 symbols DB-confirmed affected.
"""

from utils.external.fx_rates import MAJOR_CURRENCIES, FxRateCache


class _FakeResponse:
    def __init__(self, status_code: int, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self):
        return self._json_data


class _FakeSession:
    def __init__(self, rate: float | None = None, status_code: int = 200):
        self._rate = rate
        self._status_code = status_code
        self.calls = 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        currency = params["to"]
        if self._rate is None:
            return _FakeResponse(404)
        return _FakeResponse(self._status_code, {"rates": {currency: self._rate}})


def _isolated_cache(session) -> FxRateCache:
    """A FxRateCache that ignores the real shared %TEMP% cache file - this process's
    other real lookups (e.g. via sec_statements.py) may have already populated it with
    genuine rates for the same (currency, date) pairs these tests use, which would
    silently bypass the fake session and make these tests flaky/order-dependent."""
    cache = FxRateCache(session=session)
    cache._cache = {}
    return cache


class TestFxRateCache:
    def test_major_currency_converts_via_historical_rate(self):
        session = _FakeSession(rate=1.386)
        cache = _isolated_cache(session)
        rate = cache.get_usd_rate("CAD", "2025-12-31")
        assert rate == 1.386
        assert session.calls == 1

    def test_second_lookup_same_key_is_cached(self, monkeypatch):
        session = _FakeSession(rate=1.386)
        cache = _isolated_cache(session)
        monkeypatch.setattr(cache, "_save_to_file", lambda: None)
        cache.get_usd_rate("CAD", "2025-12-31")
        cache.get_usd_rate("CAD", "2025-12-31")
        assert session.calls == 1

    def test_non_major_currency_never_calls_network(self):
        session = _FakeSession(rate=1234.5)  # would be a plausible KRW-style rate
        cache = _isolated_cache(session)
        assert cache.get_usd_rate("KRW", "2025-12-31") is None
        assert session.calls == 0

    def test_missing_historical_rate_fails_closed(self):
        session = _FakeSession(rate=None)  # simulates a 404 - date outside range
        cache = _isolated_cache(session)
        assert cache.get_usd_rate("CAD", "1990-01-01") is None

    def test_every_major_currency_is_a_real_iso_code(self):
        for code in MAJOR_CURRENCIES:
            assert len(code) == 3
            assert code.isalpha()
            assert code.isupper()
