"""Regression test: preferred-share tickers using a "$" series suffix (SCE$L, BAC$L) must
resolve to their real CIK via SEC's "-P" convention (SCE-PL, BAC-PL).

Found live 2026-09-10 (XBRL missing-data audit): symbol_to_cik() had a dot->dash fallback
for dual-class tickers but no equivalent for the "$"-series preferred-share spelling used
by our market-data feed. SCE$L (Southern California Edison Series L preferred, real CIK
92103 - confirmed via SEC's own company_tickers.json listing it under ticker "SCE-PL") was
raising cik_not_found and blocking every SEC/XBRL-derived quality/value metric for it.
"""

from utils.external.sec_ticker_cache import TickerCache


def _cache_with(mapping: dict[str, str]) -> TickerCache:
    cache = TickerCache.__new__(TickerCache)
    cache._ticker_cache = mapping
    cache._ticker_cache_time = 9999999999.0  # far future - never expires in this test
    cache._cache_ttl = 86400
    return cache


class TestDollarPreferredFallback:
    def test_dollar_ticker_resolves_via_dash_p_variant(self):
        cache = _cache_with({"SCE-PL": "0000092103"})
        assert cache.symbol_to_cik("SCE$L") == "0000092103"

    def test_exact_match_still_takes_priority_over_dollar_fallback(self):
        cache = _cache_with({"SCE$L": "0000011111", "SCE-PL": "0000092103"})
        assert cache.symbol_to_cik("SCE$L") == "0000011111"

    def test_no_dash_p_variant_raises_same_as_before(self):
        cache = _cache_with({"AAPL": "0000320193"})
        cache._lookup_via_browse_edgar = lambda symbol: None
        try:
            cache.symbol_to_cik("ZZZZ$Q")
            raised = False
        except ValueError:
            raised = True
        assert raised, "a $-suffixed ticker with no -P variant must still fail closed, not fabricate a CIK"

    def test_undollared_ticker_unaffected(self):
        cache = _cache_with({"AAPL": "0000320193"})
        assert cache.symbol_to_cik("AAPL") == "0000320193"
