"""Regression test: a ticker missing from BOTH the bulk ticker file AND browse-edgar's
CIK=<ticker> company search can still resolve via SEC's EDGAR full-text search API
(efts.sec.gov), which indexes actual filing text and can surface a "(NASDAQ: XYZ)"-style
mention neither of the other two sources carries.

Found 2026-09-11 (goal: "SEC/XBRL missing data under 300" push - "resources we should be
tapping into" ask), live-confirmed against NBN (Northeast Bank): browse-edgar returns "No
matching Ticker Symbol" for CIK=NBN, but full-text search surfaces a real "NASDAQ: NBN"
mention. Also live-confirmed WHY this fallback needs deliberately stricter (fail-closed,
not fail-open) verification than _verify_ticker_matches_cik: full-text search's own top
hit for "NASDAQ: NBN" is CIK 811831 ("NORTHEAST BANCORP /ME/"), a dead entity that
deregistered via Form 15-12B in 2019 and whose submissions.json tickers array is empty -
the existing fail-open verification would have silently accepted this wrong, 7-year-stale
CIK. See _lookup_via_full_text_search's own docstring in sec_ticker_cache.py for the full
trail.
"""

import requests

from utils.external.sec_ticker_cache import TickerCache


class _FakeResponse:
    def __init__(self, status_code: int, json_data=None):
        self.status_code = status_code
        self._json_data = json_data

    def json(self):
        if self._json_data is None:
            raise ValueError("no json_data configured on this fake response")
        return self._json_data


class _FakeSession:
    """Routes by URL: efts.sec.gov full-text search vs. data.sec.gov/submissions
    verification. `search_response` is the full-text-search hit list; `verify_responses`
    maps a CIK string to its own submissions.json fake response."""

    def __init__(self, search_response=None, verify_responses=None, exc=None):
        self._search_response = search_response
        self._verify_responses = verify_responses or {}
        self._exc = exc
        self.calls = 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        if self._exc:
            raise self._exc
        if "efts.sec.gov" in url:
            return self._search_response
        for cik, resp in self._verify_responses.items():
            if cik in url:
                return resp
        return _FakeResponse(404)


def _cache_with(session=None) -> TickerCache:
    cache = TickerCache.__new__(TickerCache)
    cache._ticker_cache = {"AAPL": "0000320193"}
    cache._ticker_cache_time = 9999999999.0
    cache._cache_ttl = 86400
    cache._timeout = 10.0
    cache._rate_limiter = None
    cache._session = session or _FakeSession()
    # Browse-edgar (tried first) never resolves in these tests - isolates the full-text
    # tier under test, same stubbing approach test_sec_ticker_cache_dual_class_dot_dash.py/
    # test_sec_ticker_cache_dollar_preferred_fallback.py use for the reverse case.
    cache._lookup_via_browse_edgar = lambda symbol: None
    return cache


def _hits(*display_name_lists: list[str]) -> _FakeResponse:
    return _FakeResponse(
        200,
        json_data={"hits": {"hits": [{"_source": {"display_names": d}} for d in display_name_lists]}},
    )


class TestFullTextSearchFallback:
    def test_resolves_via_current_confirmed_filer(self, monkeypatch):
        session = _FakeSession(
            search_response=_hits(["Some Corp  (AEP)  (CIK 0000004904)"]),
            verify_responses={
                "0000004904": _FakeResponse(
                    200, json_data={"tickers": ["AEP"], "filings": {"recent": {"filingDate": ["2026-08-01"]}}}
                )
            },
        )
        cache = _cache_with(session=session)
        monkeypatch.setattr(cache, "_save_ticker_cache_to_file", lambda: None)

        assert cache.symbol_to_cik("AEP") == "0000004904"

    def test_rejects_deregistered_entity_with_stale_ticker_match(self):
        """The NBN case: full-text search's top hit is a real historical mention, but the
        candidate CIK's own tickers array is empty AND its last filing is a 2019
        deregistration - must fail closed, not silently resolve to a dead entity."""
        session = _FakeSession(
            search_response=_hits(["NORTHEAST BANCORP /ME/  (CIK 0000811831)"]),
            verify_responses={
                "0000811831": _FakeResponse(
                    200, json_data={"tickers": [], "filings": {"recent": {"filingDate": ["2019-05-21"]}}}
                )
            },
        )
        cache = _cache_with(session=session)

        try:
            cache.symbol_to_cik("NBN")
            raised = False
        except ValueError:
            raised = True
        assert raised, "a stale/deregistered full-text-search match must fail closed, not fabricate a CIK"

    def test_rejects_match_whose_tickers_array_lacks_the_queried_symbol(self):
        """A recent filer that just doesn't happen to carry this ticker (a coincidental
        name/text match) must also fail closed - the tickers check is never fail-open here,
        unlike _verify_ticker_matches_cik's browse-edgar-specific leniency."""
        session = _FakeSession(
            search_response=_hits(["Unrelated Co  (CIK 0001234567)"]),
            verify_responses={
                "0001234567": _FakeResponse(
                    200, json_data={"tickers": ["OTHR"], "filings": {"recent": {"filingDate": ["2026-08-01"]}}}
                )
            },
        )
        cache = _cache_with(session=session)

        try:
            cache.symbol_to_cik("NOTOTHR")
            raised = False
        except ValueError:
            raised = True
        assert raised

    def test_no_search_hits_fails_closed(self):
        session = _FakeSession(search_response=_hits())
        cache = _cache_with(session=session)

        try:
            cache.symbol_to_cik("NOTAREALTICKERXYZ")
            raised = False
        except ValueError:
            raised = True
        assert raised

    def test_network_error_fails_closed_not_crashing(self):
        session = _FakeSession(exc=requests.ConnectionError("no network"))
        cache = _cache_with(session=session)

        try:
            cache.symbol_to_cik("AEP")
            raised = False
        except ValueError:
            raised = True
        assert raised

    def test_exact_match_never_triggers_full_text_search_network_call(self):
        session = _FakeSession(exc=RuntimeError("should never be called"))
        cache = _cache_with(session=session)

        assert cache.symbol_to_cik("AAPL") == "0000320193"
        assert session.calls == 0
