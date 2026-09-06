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
        # ARS: still deliberately excluded (real currency volatility fails the volatility bar
        # on its own merits regardless of data source - see fx_rates.py's 2026-09-06 docstring
        # entry re-checking ARS against yfinance and rejecting it again). CLP moved onto the
        # yfinance-only major-currency set 2026-09-06 - see
        # test_clp_is_a_major_currency_and_converts_via_yfinance below.
        session = _FakeSession(rate=1234.5)  # would be a plausible ARS-style rate
        cache = _isolated_cache(session)
        assert cache.get_usd_rate("ARS", "2025-12-31") is None
        assert session.calls == 0

    def test_krw_is_a_major_currency_and_converts_via_historical_rate(self):
        # FIX 2026-08-18: KRW moved off the "deliberately not extended" list - see
        # fx_rates.py's module docstring for the live-verification (KEP/KB/SHG) behind
        # this. Frankfurter covers it and it's not meaningfully more volatile than JPY,
        # already on this list.
        session = _FakeSession(rate=0.00077)
        cache = _isolated_cache(session)
        rate = cache.get_usd_rate("KRW", "2025-12-31")
        assert rate == 0.00077
        assert session.calls == 1

    def test_cny_is_a_major_currency_and_converts_via_historical_rate(self):
        # FIX 2026-08-20: CNY added - see fx_rates.py's module docstring for the live-
        # verification (GDS Holdings' full 2016-2025 revenue history, tagged exclusively
        # in CNY, converting to a smooth $152M->$1.63B growth curve) behind this. Frankfurter
        # covers it and its year-over-year moves (<=~8%, 2018-2025) are narrower than JPY's
        # or KRW's, both already on this list.
        session = _FakeSession(rate=7.001)
        cache = _isolated_cache(session)
        rate = cache.get_usd_rate("CNY", "2025-12-31")
        assert rate == 7.001
        assert session.calls == 1

    def test_zar_is_a_major_currency_and_converts_via_historical_rate(self):
        # FIX 2026-08-22: ZAR added - see fx_rates.py's module docstring for the live-
        # verification (Harmony Gold Mining/HMY's real revenue history from FY2019 onward,
        # tagged exclusively in ZAR, converting to a plausible ~$4.16B FY2025 figure
        # consistent with its known real financials). Frankfurter covers it and its
        # year-over-year moves (2.6%-8.6%, 2019-2025 live-checked) are comparable to CNY's
        # band, already on this list.
        session = _FakeSession(rate=17.78)
        cache = _isolated_cache(session)
        rate = cache.get_usd_rate("ZAR", "2025-06-30")
        assert rate == 17.78
        assert session.calls == 1

    def test_dkk_is_a_major_currency_and_converts_via_historical_rate(self):
        # FIX 2026-09-02: DKK added - see fx_rates.py's module docstring for the live-
        # verification (Novo Nordisk/NVO's real income statement + balance sheet, tagged
        # exclusively in DKK, unlocking non-None revenue/net_income/stockholders_equity
        # for the first time) behind this. Frankfurter covers it and its year-over-year
        # moves (+6.19%/-3.26%/+6.43%, 2021-2024 live-checked) are comparable to CNY's/
        # ZAR's band, both already on this list - DKK is also ERM II-pegged to EUR within
        # a tight +/-2.25% band, structurally one of the most stable currencies here.
        session = _FakeSession(rate=7.1786)
        cache = _isolated_cache(session)
        rate = cache.get_usd_rate("DKK", "2024-12-31")
        assert rate == 7.1786
        assert session.calls == 1

    def test_hkd_is_a_major_currency_and_converts_via_historical_rate(self):
        # FIX 2026-09-02: HKD added - see fx_rates.py's module docstring for the live-
        # verification (TDIC, a small HK-listed 20-F filer, unlocking non-None revenue/
        # net_income for the first time) behind this. Frankfurter covers it and its
        # year-over-year moves (<=~0.6%, 2021-2024 live-checked) are the tightest of any
        # currency on this list - Hong Kong's currency board has pegged HKD to USD within
        # a ~7.75-7.85 band since 1983.
        session = _FakeSession(rate=7.7665)
        cache = _isolated_cache(session)
        rate = cache.get_usd_rate("HKD", "2024-12-31")
        assert rate == 7.7665
        assert session.calls == 1

    def test_brl_is_a_major_currency_and_converts_via_historical_rate(self):
        # ADDED 2026-09-04: BRL added - see fx_rates.py's module docstring for the full
        # reasoning. Reverses the 2026-08-29 rejection: the volatility finding itself
        # (28-29% year-over-year swings) is unchanged, but this is now an explicit,
        # informed product decision to accept that noise in exchange for real balance-
        # sheet/income-statement data for ~15+ Brazilian ADRs (ABEV/BBD/STNE/SUZ/CIG/VIV/
        # XP/AZUL/TIMB/PAGS/...) that were otherwise permanently NULL. Frankfurter covers
        # BRL (live-confirmed) and each fact is still converted at its own real historical
        # date-of-record rate, never a guessed/current rate.
        session = _FakeSession(rate=6.1847)
        cache = _isolated_cache(session)
        rate = cache.get_usd_rate("BRL", "2024-12-31")
        assert rate == 6.1847
        assert session.calls == 1

    def test_ils_is_a_major_currency_and_converts_via_historical_rate(self):
        # FIX 2026-09-06: ILS added - see fx_rates.py's module docstring for the full
        # live-verification (SVRE/SaverOne 2014's real ifrs-full Assets/Equity facts,
        # tagged exclusively in ILS, unlocking a real quality_metrics/growth_metrics
        # balance-sheet row for the first time). Frankfurter covers ILS and its
        # year-over-year moves (-7.9% to +13.4%, 2018-2024 live-checked) are comparable
        # to INR's/ZAR's already-accepted band, well inside BRL/MXN's rejected 20%+ band.
        session = _FakeSession(rate=3.6466)
        cache = _isolated_cache(session)
        rate = cache.get_usd_rate("ILS", "2024-12-31")
        assert rate == 3.6466
        assert session.calls == 1

    def test_ars_stays_excluded_no_frankfurter_coverage(self):
        # ARS was evaluated alongside BRL in the same 2026-09-04 session and stays
        # excluded: unlike BRL, this was a structural source-availability gap, not a
        # volatility judgment - Frankfurter returns {"message": "not found"} for ARS
        # (live-confirmed `GET /2024-12-31?from=USD&to=ARS`), same as COP/TWD (CLP/KZT
        # were the same Frankfurter gap but moved onto MAJOR_CURRENCIES 2026-09-06 via a
        # yfinance fallback - see test_clp_is_a_major_currency_and_converts_via_yfinance
        # below; ARS itself was separately re-checked against yfinance that same day and
        # rejected again on volatility grounds instead - see fx_rates.py's docstring).
        # No Frankfurter policy decision can fix a data source that doesn't exist.
        session = _FakeSession(rate=1000.0)
        cache = _isolated_cache(session)
        assert cache.get_usd_rate("ARS", "2024-12-31") is None
        assert session.calls == 0

    def test_clp_is_a_major_currency_and_converts_via_yfinance(self, monkeypatch):
        # FIX 2026-09-06: CLP added via yfinance (Frankfurter has no CLP listing at all,
        # confirmed via `GET /v1/currencies` - see fx_rates.py's module docstring for the
        # live BCH verification behind this). Routes through _fetch_rate_yfinance, not the
        # Frankfurter _session path, so this must mock yfinance.Ticker directly rather than
        # _FakeSession - without this, get_usd_rate("CLP", ...) falls through to a REAL
        # network call to Yahoo Finance (live-observed during this session's own test run).
        import pandas as pd

        from utils.external import fx_rates as fx_rates_module

        history = pd.DataFrame(
            {"Close": [1004.13]},
            index=pd.DatetimeIndex([pd.Timestamp("2024-12-31")]),
        )

        class _FakeTicker:
            def __init__(self, symbol):
                self.symbol = symbol

            def history(self, start, end):
                return history

        monkeypatch.setattr(fx_rates_module.yfinance, "Ticker", _FakeTicker)
        cache = _isolated_cache(_FakeSession(rate=None))
        rate = cache.get_usd_rate("CLP", "2024-12-31")
        assert rate == 1004.13

    def test_kzt_is_a_major_currency_and_converts_via_yfinance(self, monkeypatch):
        # Same yfinance-fallback path as CLP above - see fx_rates.py's module docstring
        # for the live KSPI verification behind adding KZT.
        import pandas as pd

        from utils.external import fx_rates as fx_rates_module

        history = pd.DataFrame(
            {"Close": [521.98]},
            index=pd.DatetimeIndex([pd.Timestamp("2024-12-31")]),
        )

        class _FakeTicker:
            def __init__(self, symbol):
                self.symbol = symbol

            def history(self, start, end):
                return history

        monkeypatch.setattr(fx_rates_module.yfinance, "Ticker", _FakeTicker)
        cache = _isolated_cache(_FakeSession(rate=None))
        rate = cache.get_usd_rate("KZT", "2024-12-31")
        assert rate == 521.98

    def test_yfinance_currency_empty_history_fails_closed(self, monkeypatch):
        # A date outside the ticker's published range (or a yfinance outage/empty
        # response) must never be silently guessed at - same fail-closed discipline as
        # the Frankfurter 404 path.
        import pandas as pd

        from utils.external import fx_rates as fx_rates_module

        class _FakeTicker:
            def __init__(self, symbol):
                self.symbol = symbol

            def history(self, start, end):
                return pd.DataFrame({"Close": []}, index=pd.DatetimeIndex([]))

        monkeypatch.setattr(fx_rates_module.yfinance, "Ticker", _FakeTicker)
        cache = _isolated_cache(_FakeSession(rate=None))
        assert cache.get_usd_rate("CLP", "2024-12-31") is None

    def test_sek_stays_excluded_too_volatile(self):
        # SEK was checked as a DKK/HKD-adjacent candidate (Ericsson reports in SEK, same
        # zeroed-statement shape) and does NOT clear the bar - see fx_rates.py's module
        # docstring: -12.07%/+15.22% year-over-year moves exceed every currency already
        # accepted here (INR's 11.1% was the prior ceiling). Stays excluded, not a bug.
        session = _FakeSession(rate=11.03)
        cache = _isolated_cache(session)
        assert cache.get_usd_rate("SEK", "2024-12-31") is None
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
