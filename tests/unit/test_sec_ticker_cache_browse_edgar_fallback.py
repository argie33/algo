"""Regression test: tickers missing from BOTH of SEC's own bulk ticker files
(company_tickers.json and company_tickers_exchange.json) must still resolve via a
browse-edgar fallback rather than permanently failing.

Found live 2026-08-17: SEC's own "complete" ticker files are missing real, actively-traded,
large-cap tickers entirely - AEP (American Electric Power, NYSE, S&P 500 utility), PARA
(Paramount Global), JHG (Janus Henderson), AMWD, KFS, KW, NSA all confirmed absent from both
files via a live fetch, yet all resolve to real 10-K filers via SEC's legacy browse-edgar
company search (which accepts a ticker directly in its CIK= parameter). A live DB scan found
149 symbols with reason='cik_not_found' in annual_income_statement, 59 of them plain/
undecorated tickers - too many for the existing manual CIK_OVERRIDES map to keep up with, so
symbol_to_cik() now tries this endpoint as a last resort before failing closed.
"""

import requests

from utils.external.sec_ticker_cache import TickerCache


class _FakeResponse:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text


class _FakeSession:
    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc
        self.calls = 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        if self._exc:
            raise self._exc
        return self._response


def _cache_with(mapping: dict[str, str], session=None) -> TickerCache:
    cache = TickerCache.__new__(TickerCache)
    cache._ticker_cache = mapping
    cache._ticker_cache_time = 9999999999.0  # far future - never expires in this test
    cache._cache_ttl = 86400
    cache._timeout = 10.0
    cache._rate_limiter = None
    cache._session = session or _FakeSession()
    return cache


class TestBrowseEdgarFallback:
    def test_ticker_missing_from_bulk_file_resolves_via_browse_edgar(self, monkeypatch):
        atom = "<feed><company-info><cik>0000004904</cik></company-info></feed>"
        session = _FakeSession(_FakeResponse(200, atom))
        cache = _cache_with({"AAPL": "0000320193"}, session=session)
        monkeypatch.setattr(cache, "_save_ticker_cache_to_file", lambda: None)

        assert cache.symbol_to_cik("AEP") == "0000004904"
        assert session.calls == 1

    def test_successful_fallback_is_cached_for_next_lookup(self, monkeypatch):
        atom = "<feed><company-info><cik>0000004904</cik></company-info></feed>"
        session = _FakeSession(_FakeResponse(200, atom))
        cache = _cache_with({}, session=session)
        monkeypatch.setattr(cache, "_save_ticker_cache_to_file", lambda: None)

        assert cache.symbol_to_cik("AEP") == "0000004904"
        assert cache._ticker_cache["AEP"] == "0000004904"
        # Second lookup must hit the in-memory cache, not the network again.
        assert cache.symbol_to_cik("AEP") == "0000004904"
        assert session.calls == 1

    def test_genuinely_nonexistent_ticker_still_fails_closed(self):
        atom = "<feed></feed>"  # no <cik> tag - real "not found" response shape
        session = _FakeSession(_FakeResponse(200, atom))
        cache = _cache_with({"AAPL": "0000320193"}, session=session)

        try:
            cache.symbol_to_cik("NOTAREALTICKERXYZ")
            raised = False
        except ValueError:
            raised = True
        assert raised, "a ticker unresolvable via both the bulk file and the fallback must fail closed"

    def test_network_error_falls_back_to_failing_closed_not_crashing(self):
        session = _FakeSession(exc=requests.ConnectionError("no network"))
        cache = _cache_with({"AAPL": "0000320193"}, session=session)

        try:
            cache.symbol_to_cik("AEP")
            raised = False
        except ValueError:
            raised = True
        assert raised, "a transient network error in the fallback must still raise ValueError, not crash"

    def test_exact_match_never_triggers_fallback_network_call(self):
        session = _FakeSession(exc=RuntimeError("should never be called"))
        cache = _cache_with({"AAPL": "0000320193"}, session=session)

        assert cache.symbol_to_cik("AAPL") == "0000320193"
        assert session.calls == 0
