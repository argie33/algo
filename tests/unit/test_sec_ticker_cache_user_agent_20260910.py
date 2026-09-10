"""Regression test: TickerCache's requests.Session must carry a SEC-compliant User-Agent.

Found live 2026-09-10 (under-500 XBRL push, cik_not_found bucket investigation): this
module's session never set a User-Agent header, unlike sec_edgar_client.py's
DEFAULT_USER_AGENT (same env var, same default contact string). www.sec.gov/files/
company_tickers.json (a static file) tolerates the resulting bare "python-requests/x.x"
UA, which is why the bulk-file fast path kept working and this went unnoticed - but
browse-edgar (_lookup_via_browse_edgar's last-resort fallback for tickers missing from
the bulk file) and data.sec.gov/submissions (_verify_ticker_matches_cik) both hard-reject
a bare UA with HTTP 403, live-confirmed via real symbols (FRBA/HIFS/KRSA/NBN/NXAT/RCBC/
SSBI/TOWN): identical requests.get returned 403 with no UA, 200 with one. Every symbol
relying on this fallback was silently unable to ever resolve via it.
"""

from utils.external.sec_ticker_cache import DEFAULT_USER_AGENT, TickerCache


class TestTickerCacheUserAgent:
    def test_init_sets_user_agent_on_own_session(self, tmp_path, monkeypatch):
        monkeypatch.setattr(TickerCache, "_load_ticker_cache_from_file", lambda self: None)
        cache = TickerCache()
        assert cache._session.headers.get("User-Agent") == DEFAULT_USER_AGENT
        assert "@" in DEFAULT_USER_AGENT

    def test_init_overrides_caller_supplied_session_default_user_agent(self, monkeypatch):
        import requests

        monkeypatch.setattr(TickerCache, "_load_ticker_cache_from_file", lambda self: None)
        caller_session = requests.Session()
        # A plain requests.Session() carries requests' own default bare UA
        # ("python-requests/x.y.z") - exactly the shape SEC's browse-edgar/submissions
        # endpoints 403 on, so this must get overwritten, not left alone.
        assert caller_session.headers.get("User-Agent", "").startswith("python-requests")
        cache = TickerCache(session=caller_session)
        assert cache._session.headers.get("User-Agent") == DEFAULT_USER_AGENT
