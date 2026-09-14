"""Regression test for a live-confirmed bug found 2026-09-14: load_market_constituents.py's
fetch_global has a secondary name-based fund/ETF catch (is_fund_or_etf_by_name, separate from
should_exclude()/EXCLUSION_PATTERNS - see test_market_constituents_exclusion_patterns.py) that
used a plain substring check (`"etf" in name.lower()`), which matched "Netflix, Inc. - Common
Stock" purely because "etf" is a literal substring of "n-ETF-lix" - nothing to do with being an
ETF or fund. This silently dropped NFLX (a real, liquid mega-cap, present with clean Test
Issue=N/Financial Status=N/ETF=N fields in the real upstream NASDAQ feed) from stock_symbols
entirely - zero row, not just active=false - so every downstream pillar/score for NFLX was
simply absent. A live sweep of the full current nasdaqlisted.txt+otherlisted.txt universe
found NFLX was the only "etf"-substring false positive and confirmed zero "fund"-substring
false positives exist (every other "fund" hit is a real closed-end fund/BDC name, correctly
excluded on other grounds). Fixed via word-boundary regex, matching EXCLUSION_PATTERNS' own
`\\bfund\\b` convention (which already deliberately dropped a bare `\\betf\\b` for the identical
false-positive reason - see its own NOTE) - extracted to its own module purely to keep
load_market_constituents.py (already-oversized legacy debt) from growing further.
"""

from loaders.helpers.market_constituents_name_filters import is_fund_or_etf_by_name


class TestFundOrEtfByNameSubstringCollision:
    def test_netflix_not_excluded(self):
        assert not is_fund_or_etf_by_name("Netflix, Inc. - Common Stock")

    def test_real_fund_names_still_excluded(self):
        assert is_fund_or_etf_by_name("Sprott Focus Trust, Inc. - Closed End Fund")
        assert is_fund_or_etf_by_name("Nuveen NASDAQ 100 Dynamic Overwrite Fund - Closed End Fund")

    def test_real_etf_named_security_still_excluded(self):
        assert is_fund_or_etf_by_name("Some Example ETF Common Shares")

    def test_other_etf_substring_collisions_not_excluded(self):
        """Other real, non-fund company names that happen to contain the "etf" substring
        must not be caught either - the fix is general (word-boundary), not a NFLX-specific
        carve-out."""
        assert not is_fund_or_etf_by_name("Betfair Interactive US LLC - Common Stock")
