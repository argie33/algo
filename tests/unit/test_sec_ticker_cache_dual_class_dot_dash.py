"""Regression test: dual-class tickers using a dot (BRK.A, TAP.A) must resolve to their
real CIK via SEC's dash convention (BRK-A, TAP-A).

Found live 2026-07-28: symbol_to_cik() did an exact-match lookup against SEC's
company_tickers.json with no normalization, so any dotted dual-class ticker missed
entirely (SEC's own file spells these with a dash, not a dot). Live-confirmed 23 of 39
dotted tickers reporting value_metrics.data_unavailable="missing_sec_data" resolve
correctly once the dot is swapped for a dash - including BRK.A/BRK.B (Berkshire
Hathaway has no undotted ticker at all, so this masked SEC data for one of the largest
companies in the market). The remaining dotted tickers are ".R" (rights) suffixes with
no separate SEC ticker entry at all - correctly still unresolved, not fabricated.
"""

from utils.external.sec_ticker_cache import TickerCache


def _cache_with(mapping: dict[str, str]) -> TickerCache:
    cache = TickerCache.__new__(TickerCache)
    cache._ticker_cache = mapping
    cache._ticker_cache_time = 9999999999.0  # far future - never expires in this test
    cache._cache_ttl = 86400
    return cache


class TestDualClassDotDashFallback:
    def test_dotted_ticker_resolves_via_dash_variant(self):
        cache = _cache_with({"BRK-A": "0001067983", "BRK-B": "0001067983"})
        assert cache.symbol_to_cik("BRK.A") == "0001067983"
        assert cache.symbol_to_cik("BRK.B") == "0001067983"

    def test_exact_match_still_takes_priority_over_dash_fallback(self):
        # If SEC's file ever DOES have a literal dotted entry, don't override it with a
        # dash-swapped false match.
        cache = _cache_with({"TAP.A": "0000111111", "TAP-A": "0000024545"})
        assert cache.symbol_to_cik("TAP.A") == "0000111111"

    def test_no_dash_variant_raises_same_as_before(self):
        cache = _cache_with({"AAPL": "0000320193"})
        # The browse-edgar fallback (see test_sec_ticker_cache_browse_edgar_fallback.py) is
        # network-dependent and covered separately - stub it here so this test stays a fast,
        # deterministic check of the dot/dash logic alone, not an integration test.
        cache._lookup_via_browse_edgar = lambda symbol: None
        try:
            cache.symbol_to_cik("XFLH.R")
            raised = False
        except ValueError:
            raised = True
        assert raised, "a dotted ticker with no dash variant must still fail closed, not fabricate a CIK"

    def test_undotted_ticker_unaffected(self):
        cache = _cache_with({"AAPL": "0000320193"})
        assert cache.symbol_to_cik("AAPL") == "0000320193"
