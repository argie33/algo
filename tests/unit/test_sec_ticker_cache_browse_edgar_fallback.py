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
    def __init__(self, status_code: int, text: str = "", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json_data = json_data

    def json(self):
        if self._json_data is None:
            raise ValueError("no json_data configured on this fake response")
        return self._json_data


class _FakeSession:
    """Routes by URL: browse-edgar's atom XML response vs. the CIK-verification
    submissions.json response the 2026-08-31 fix added. `verify_response` defaults to a
    ticker list containing whatever ticker the browse-edgar atom's CIK would plausibly
    match, so tests written before the verification fix keep passing it by default -
    tests that specifically want to exercise a verification MISMATCH pass their own.
    """

    def __init__(self, response=None, exc=None, verify_response=None):
        self._response = response
        self._exc = exc
        self._verify_response = verify_response
        self.calls = 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        if self._exc:
            raise self._exc
        if "data.sec.gov/submissions" in url:
            return self._verify_response if self._verify_response is not None else _FakeResponse(404)
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
        # 1 browse-edgar call + 1 CIK-verification call (2026-08-31 fix) - no
        # verify_response configured, so verification fails open (404 -> True).
        assert session.calls == 2

    def test_successful_fallback_is_cached_for_next_lookup(self, monkeypatch):
        atom = "<feed><company-info><cik>0000004904</cik></company-info></feed>"
        session = _FakeSession(_FakeResponse(200, atom))
        cache = _cache_with({}, session=session)
        monkeypatch.setattr(cache, "_save_ticker_cache_to_file", lambda: None)

        assert cache.symbol_to_cik("AEP") == "0000004904"
        assert cache._ticker_cache["AEP"] == "0000004904"
        # Second lookup must hit the in-memory cache, not the network again.
        assert cache.symbol_to_cik("AEP") == "0000004904"
        assert session.calls == 2

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


class TestBrowseEdgarFallbackRejectsMismatchedCik:
    """Regression test for the 2026-08-31 fix (goal session: "get all the data we need"
    full-coverage audit): browse-edgar's CIK=<symbol> search silently falls back to a
    company-name/prefix search for a symbol it can't exact-match, with no exactness
    guarantee - live-confirmed via real SEC data three separate ways: "IAC" (should be
    IAC/InterActiveCorp) resolved to CIK 1800227, whose own submissions.json lists ticker
    "PPLI" (People Inc), not "IAC"; "DMC" and "FDP" (DMC Global and Fresh Del Monte
    Produce, two unrelated real companies) both resolved to CIK 1047340 (Del Monte
    Corporation, an unrelated third company). Each pair then silently shared one
    company's entire financial history in annual_income_statement (byte-for-byte
    identical revenue for 2-4 consecutive fiscal years) - the same corruption signature
    as the WTRG/AWK 8-K bug fixed the same session, different root cause. Fix: verify the
    resolved CIK's own submissions record actually lists the queried ticker before
    trusting it; reject (fail closed) if it positively contradicts, same as a genuinely
    unresolvable ticker.
    """

    def test_rejects_a_cik_whose_own_tickers_dont_include_the_queried_symbol(self):
        atom = "<feed><company-info><cik>0001800227</cik></company-info></feed>"
        verify_response = _FakeResponse(200, json_data={"tickers": ["PPLI"]})
        session = _FakeSession(_FakeResponse(200, atom), verify_response=verify_response)
        cache = _cache_with({"AAPL": "0000320193"}, session=session)

        try:
            cache.symbol_to_cik("IAC")
            raised = False
        except ValueError:
            raised = True
        assert raised, "a browse-edgar match whose own CIK doesn't list the queried ticker must fail closed"

    def test_accepts_a_cik_whose_own_tickers_do_include_the_queried_symbol(self, monkeypatch):
        atom = "<feed><company-info><cik>0000004904</cik></company-info></feed>"
        verify_response = _FakeResponse(200, json_data={"tickers": ["AEP"]})
        session = _FakeSession(_FakeResponse(200, atom), verify_response=verify_response)
        cache = _cache_with({"AAPL": "0000320193"}, session=session)
        monkeypatch.setattr(cache, "_save_ticker_cache_to_file", lambda: None)

        assert cache.symbol_to_cik("AEP") == "0000004904"

    def test_verification_network_error_fails_open_not_closed(self, monkeypatch):
        """A flaky/unavailable verification endpoint must not turn every fallback
        resolution into a failure - it's a safety net against one known bug, not a new
        hard dependency."""
        atom = "<feed><company-info><cik>0000004904</cik></company-info></feed>"

        class _FlakyVerifySession(_FakeSession):
            def get(self, url, params=None, timeout=None):
                if "data.sec.gov/submissions" in url:
                    raise requests.Timeout("slow")
                return super().get(url, params=params, timeout=timeout)

        session = _FlakyVerifySession(_FakeResponse(200, atom))
        cache = _cache_with({"AAPL": "0000320193"}, session=session)
        monkeypatch.setattr(cache, "_save_ticker_cache_to_file", lambda: None)

        assert cache.symbol_to_cik("AEP") == "0000004904"
