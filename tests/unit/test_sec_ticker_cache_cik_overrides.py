"""Regression test for a real, live-reproduced bug (2026-07-27): SEC's own
company_tickers.json maps ticker "XOM" to CIK 2115436 ("ExxonMobil Holdings Corp"),
a non-10-K-filing subsidiary (zero us-gaap XBRL facts, filings are almost entirely
"S-8 POS" stock-plan amendments) - not the real, publicly-traded Exxon Mobil Corp
(CIK 34088, the actual 10-K filer). Confirmed live: CIK 34088 doesn't appear under
any ticker in SEC's own ticker file at all.

This had already silently corrupted company_info_sec.entity_name (stored as
"ExxonMobil Holdings Corp") and left shares_outstanding NULL for XOM while still
marking the row data_unavailable=FALSE - and caused load_sec_segment_info.py to
report data_unavailable("no_us_gaap_facts") for one of the market's largest,
most heavily-covered stocks. Spot-checked 12 other large caps
(CVX/JPM/WMT/KO/PG/GE/DIS/JNJ/PFE/MRK/T/VZ) - all resolved correctly, so this is a
one-off SEC data quirk specific to XOM's corporate history, not a systemic
duplicate-ticker collision bug in TickerCache's cache-building logic.

Fixed via a small, explicit, manually-verified CIK_OVERRIDES map consulted before
the normal SEC-file-backed cache lookup.
"""

from utils.external.sec_ticker_cache import CIK_OVERRIDES, TickerCache


class TestCikOverrides:
    def test_xom_overridden_to_the_real_10k_filer(self):
        cache = TickerCache.__new__(TickerCache)
        cache._ticker_cache = {}  # would raise ValueError if the override didn't short-circuit
        cache._ticker_cache_time = 0.0
        cache._cache_ttl = 86400

        assert cache.symbol_to_cik("XOM") == "0000034088"
        assert cache.symbol_to_cik("xom") == "0000034088", "override lookup must be case-insensitive"

    def test_override_does_not_affect_unrelated_symbols(self):
        cache = TickerCache.__new__(TickerCache)
        cache._ticker_cache = {"AAPL": "0000320193"}
        cache._ticker_cache_time = 9999999999.0  # far future - cache never expires in this test
        cache._cache_ttl = 86400

        assert cache.symbol_to_cik("AAPL") == "0000320193"

    def test_overrides_map_only_contains_manually_verified_entries(self):
        """Sanity guard: every override must be a real, zero-padded 10-digit CIK string -
        catches an accidental malformed entry before it reaches SEC's live API."""
        for ticker, cik in CIK_OVERRIDES.items():
            assert ticker == ticker.upper()
            assert isinstance(cik, str)
            assert len(cik) == 10
            assert cik.isdigit()
