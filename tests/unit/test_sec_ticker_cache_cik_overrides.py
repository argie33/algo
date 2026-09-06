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

    def test_dmc_shoe_grsd_overridden_to_verified_ciks(self):
        # Added 2026-08-31 following up the browse-edgar fuzzy-match fix (commit
        # 4061fd5c1, same day): once that fix started correctly rejecting unverified
        # fuzzy matches, these 3 active-universe symbols came back "CIK not found"
        # because this morning's cached company_tickers.json snapshot happened to be
        # missing them and browse-edgar's own CIK=<symbol> endpoint was returning HTTP
        # 403 at the time - not a real ambiguity. Each verified directly against
        # https://data.sec.gov/submissions/CIK<n>.json: DMC=1047340 (own
        # tickers=["DMC"], NYSE - also matches our stock_symbols.security_name "Del
        # Monte Corporation Ordinary Shares"), SHOE=895447, GRSD=1839799 (both self-
        # confirm via their own tickers arrays). See CIK_OVERRIDES's own comment for
        # why "DMC" does NOT mean DMC Global Inc (that company renamed its ticker to
        # BOOM and no longer uses "DMC" at all).
        cache = TickerCache.__new__(TickerCache)
        cache._ticker_cache = {}  # would raise ValueError if the override didn't short-circuit
        cache._ticker_cache_time = 0.0
        cache._cache_ttl = 86400

        assert cache.symbol_to_cik("DMC") == "0001047340"
        assert cache.symbol_to_cik("SHOE") == "0000895447"
        assert cache.symbol_to_cik("GRSD") == "0001839799"

    def test_hos_overridden_to_the_post_rename_cik(self):
        # Added 2026-09-05 (goal session: "SEC/XBRL missing data to zero" sweep). CIK
        # 866829 genuinely renamed itself "HORNBECK OFFSHORE SERVICES, INC." on
        # 2026-08-31 (per its own submissions.json formerNames, coming from "HELIX
        # ENERGY SOLUTIONS GROUP INC") and is still filing under that CIK (most recent
        # filing 2026-09-04). SEC's bulk company_tickers.json snapshot hasn't caught up
        # with the rename yet and still lists this CIK only under the old "HLX" ticker,
        # so a plain lookup for our tracked "HOS" symbol found nothing and fell through
        # to missing-SEC-data reasons for a company that is actively, currently filing.
        cache = TickerCache.__new__(TickerCache)
        cache._ticker_cache = {}  # would raise ValueError if the override didn't short-circuit
        cache._ticker_cache_time = 0.0
        cache._cache_ttl = 86400

        assert cache.symbol_to_cik("HOS") == "0000866829"

    def test_gv_ftrk_sgrx_overridden_to_verified_ciks(self):
        # Added 2026-09-06 (coverage campaign continuation: dividend_data/
        # current_reports_8k/company_info_sec.shares_outstanding "cik_not_found"/
        # "symbol_not_found" buckets). Same root cause as GV/HOS above - SEC's own bulk
        # company_tickers.json AND company_tickers_exchange.json list only a stale/
        # secondary ticker per CIK (checked both files directly). Each verified against
        # its own submissions.json for both an exact name match to our
        # stock_symbols.security_name AND a real, recent (2026) 10-K/6-K filing (a name
        # match alone isn't sufficient - this same session's search also surfaced
        # NBN/HIFS name-matches whose CIKs turned out to be stale shells with no recent
        # filings, deliberately NOT added here): GV=1892274 (own tickers=["GV","GVHGF"],
        # latest 10-K 2026-01-28), FTRK=2027262 (own tickers are the pre-uplisting OTC
        # classes ["FTRKF","FTRKD"], but exact unambiguous name match with no
        # formerNames history, latest 10-K 2026-06-30), SGRX=1735556 (own ticker still
        # "BTOG" pre-rename, but name="SANGRIX INC." with formerNames showing "BIT
        # ORIGIN Ltd" ending 2026-08-26, latest 10-K 2025-10-31).
        cache = TickerCache.__new__(TickerCache)
        cache._ticker_cache = {}  # would raise ValueError if the override didn't short-circuit
        cache._ticker_cache_time = 0.0
        cache._cache_ttl = 86400

        assert cache.symbol_to_cik("GV") == "0001892274"
        assert cache.symbol_to_cik("FTRK") == "0002027262"
        assert cache.symbol_to_cik("SGRX") == "0001735556"

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
