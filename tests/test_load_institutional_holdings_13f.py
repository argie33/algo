#!/usr/bin/env python3
"""Regression tests: SEC Form 13F bulk dataset discovery, parsing, and crosswalk.

Previously this loader (1) guessed the bulk dataset filename as
"{year}-Q{quarter}_FORM13FDATA.zip", which never matches SEC's real naming
convention ("01jun2025-31aug2025_form13f.zip" - a date-range tied to the 45-day
filing deadline, not a calendar-quarter label) and 404s on every real request,
and (2) parsed the downloaded TSV assuming a "ticker"/"shrsOrPrnAmt" column pair
that does not exist - real INFOTABLE.tsv columns are NAMEOFISSUER/CUSIP/SSHPRNAMT
(13F filings identify securities by CUSIP only). Confirmed live against SEC's real
listing page and a real downloaded dataset before fixing.

Later (2026-07-27), closed the standing "no free CUSIP->ticker crosswalk" gap via
OpenFIGI, cached in sec_13f_cusip_crosswalk (migration 1161) - see
_crosswalk_to_tickers tests below.
"""

from loaders.load_institutional_holdings_13f import InstitutionalHoldings13FLoader

LISTING_HTML = """
<html><body>
<a href="/files/structureddata/data/form-13f-data-sets/01mar2026-31may2026_form13f.zip">Q1 2026</a>
<a href="/files/structureddata/data/form-13f-data-sets/01dec2025-28feb2026_form13f.zip">Q4 2025</a>
<a href="/files/structureddata/data/form-13f-data-sets/01sep2025-30nov2025_form13f.zip">Q3 2025</a>
</body></html>
"""


def _make_loader() -> InstitutionalHoldings13FLoader:
    return InstitutionalHoldings13FLoader.__new__(InstitutionalHoldings13FLoader)


def test_discover_picks_the_dataset_with_latest_end_date(monkeypatch) -> None:
    loader = _make_loader()

    class _FakeResponse:
        def read(self):
            return LISTING_HTML.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=30: _FakeResponse())

    result = loader._discover_latest_13f_bulk_dataset()

    assert result is not None
    url, period_end = result
    assert url == "https://www.sec.gov/files/structureddata/data/form-13f-data-sets/01mar2026-31may2026_form13f.zip"
    assert period_end.isoformat() == "2026-05-31"


def test_parses_real_infotable_columns_keyed_by_cusip(monkeypatch) -> None:
    """INFOTABLE.tsv has no ticker column - holdings must be keyed by CUSIP."""
    import io
    import zipfile

    tsv = (
        "ACCESSION_NUMBER\tINFOTABLE_SK\tNAMEOFISSUER\tTITLEOFCLASS\tCUSIP\tFIGI\tVALUE\t"
        "SSHPRNAMT\tSSHPRNAMTTYPE\tPUTCALL\tINVESTMENTDISCRETION\tOTHERMANAGER\t"
        "VOTING_AUTH_SOLE\tVOTING_AUTH_SHARED\tVOTING_AUTH_NONE\n"
        "0001-26-000001\t1\t3M CO\tCOM\t88579Y101\t\t7377\t48\tSH\t\tSOLE\t0\t0\t0\t48\n"
        "0001-26-000002\t2\t3M CO\tCOM\t88579Y101\t\t1000\t52\tSH\t\tSOLE\t0\t0\t0\t52\n"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("01mar2026-31may2026_form13f/INFOTABLE.tsv", tsv)
    zip_bytes = buf.getvalue()

    loader = _make_loader()

    class _FakeResponse:
        def read(self):
            return zip_bytes

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=120: _FakeResponse())

    holdings, _manager_holdings = loader._fetch_and_parse_13f_bulk("https://www.sec.gov/files/.../fake.zip")

    # Both rows share CUSIP 88579Y101 (same issuer, different manager filings) -
    # must sum, not overwrite, and must be keyed by CUSIP since there is no ticker.
    assert holdings == {"88579Y101": 100}


class _FakeCrosswalkCursor:
    """Routes by query shape: cache SELECT, entity-name SELECT, or cache upsert."""

    def __init__(self, cached_rows, local_name_rows):
        self._cached_rows = cached_rows
        self._local_name_rows = local_name_rows
        self._pending_result: list = []
        self.upserts: list = []

    def execute(self, query, params=None):
        if "FROM sec_13f_cusip_crosswalk" in query:
            self._pending_result = self._cached_rows
        elif "FROM company_info_sec" in query:
            self._pending_result = self._local_name_rows
        elif "INSERT INTO sec_13f_cusip_crosswalk" in query:
            self.upserts.append(params)
        else:
            raise AssertionError(f"unexpected query: {query}")

    def fetchall(self):
        return self._pending_result


def test_crosswalk_to_tickers_uses_cache_and_only_queries_openfigi_for_new_cusips(monkeypatch):
    """A CUSIP already in sec_13f_cusip_crosswalk must not trigger a live OpenFIGI
    call - the whole point of the cache is to avoid re-crosswalking the ~34k-CUSIP
    universe every quarter."""
    loader = _make_loader()

    cursor = _FakeCrosswalkCursor(
        cached_rows=[("037833100", "AAPL", "APPLE INC")],  # already cached
        local_name_rows=[("AAPL", "Apple Inc.")],
    )

    class _FakeDatabaseContext:
        def __init__(self, mode):
            pass

        def __enter__(self):
            return cursor

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("loaders.load_institutional_holdings_13f.DatabaseContext", _FakeDatabaseContext)
    monkeypatch.setattr("loaders.load_institutional_holdings_13f.get_active_symbols", lambda exclude_etfs=True: ["AAPL"])

    def _fail_if_called(cusips):
        raise AssertionError(f"OpenFIGI should not be queried for already-cached CUSIPs, got {cusips}")

    monkeypatch.setattr("loaders.load_institutional_holdings_13f.fetch_cusip_tickers", _fail_if_called)

    result, _manager_result = loader._crosswalk_to_tickers({"037833100": 914936485})

    assert result == {"AAPL": 914936485}
    assert cursor.upserts == []  # nothing new to cache


def test_crosswalk_to_tickers_queries_and_caches_new_cusips(monkeypatch):
    """A CUSIP never seen before must trigger a live OpenFIGI call, and the result
    (including a negative/unresolved one) must be persisted to the cache table."""
    loader = _make_loader()

    cursor = _FakeCrosswalkCursor(
        cached_rows=[],  # nothing cached yet
        local_name_rows=[("AAPL", "Apple Inc.")],
    )

    class _FakeDatabaseContext:
        def __init__(self, mode):
            pass

        def __enter__(self):
            return cursor

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("loaders.load_institutional_holdings_13f.DatabaseContext", _FakeDatabaseContext)
    monkeypatch.setattr("loaders.load_institutional_holdings_13f.get_active_symbols", lambda exclude_etfs=True: ["AAPL"])
    def _fake_fetch_cusip_tickers(cusips, on_batch_resolved=None, deadline=None):
        resolved = {"037833100": {"ticker": "AAPL", "name": "APPLE INC"}}
        if on_batch_resolved is not None:
            on_batch_resolved({c: resolved.get(c) for c in cusips})
        return resolved

    monkeypatch.setattr(
        "loaders.load_institutional_holdings_13f.fetch_cusip_tickers",
        _fake_fetch_cusip_tickers,
    )

    result, _manager_result = loader._crosswalk_to_tickers({"037833100": 914936485, "UNRESOLVABLE": 500})

    assert result == {"AAPL": 914936485}
    # Both the resolved and unresolved CUSIP must be cached (a negative result is a
    # real, cacheable outcome - never re-queried again).
    cached_cusips = {call[0] for call in cursor.upserts}
    assert cached_cusips == {"037833100", "UNRESOLVABLE"}


def test_crosswalk_to_tickers_rejects_the_live_verified_xom_wrong_entity_match(monkeypatch):
    """Live-verified 2026-07-27: OpenFIGI can resolve a CUSIP to a ticker that IS in
    our tracked universe but is the WRONG entity (XOM -> a different corporate entity
    than the real 10-K filer). The name-plausibility check must reject this even
    though the ticker itself matches."""
    loader = _make_loader()

    cursor = _FakeCrosswalkCursor(
        cached_rows=[("999999999", "XOM", "EXXONMOBIL HOLDINGS CORP")],
        local_name_rows=[("XOM", "EXXON MOBIL CORP")],
    )

    class _FakeDatabaseContext:
        def __init__(self, mode):
            pass

        def __enter__(self):
            return cursor

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("loaders.load_institutional_holdings_13f.DatabaseContext", _FakeDatabaseContext)
    monkeypatch.setattr("loaders.load_institutional_holdings_13f.get_active_symbols", lambda exclude_etfs=True: ["XOM"])

    result, _manager_result = loader._crosswalk_to_tickers({"999999999": 999})

    assert result == {}


def test_crosswalk_to_tickers_ignores_a_resolved_ticker_outside_our_universe(monkeypatch):
    """Live-verified 2026-07-27: the real Exxon Mobil Corp CUSIP (30231G102) resolves
    via OpenFIGI to ticker 'EXMOC', not 'XOM' - a real Bloomberg-side ticker variant.
    A resolved ticker that isn't in our tracked universe at all must be silently
    skipped, not treated as an error."""
    loader = _make_loader()

    cursor = _FakeCrosswalkCursor(
        cached_rows=[("30231G102", "EXMOC", "EXXON MOBIL CORP")],
        local_name_rows=[("XOM", "EXXON MOBIL CORP")],
    )

    class _FakeDatabaseContext:
        def __init__(self, mode):
            pass

        def __enter__(self):
            return cursor

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("loaders.load_institutional_holdings_13f.DatabaseContext", _FakeDatabaseContext)
    monkeypatch.setattr("loaders.load_institutional_holdings_13f.get_active_symbols", lambda exclude_etfs=True: ["XOM"])

    result, _manager_result = loader._crosswalk_to_tickers({"30231G102": 5720000000})

    assert result == {}
