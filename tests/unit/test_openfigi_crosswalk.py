"""Regression tests for utils/external/openfigi_crosswalk.py.

This module closes the SEC Form 13F CUSIP->ticker crosswalk gap (previously
documented across many sessions as an "architectural impossibility" - CUSIP is
licensed, and SEC never exposes ticker in the 13F bulk dataset). Real fix,
live-verified 2026-07-27: OpenFIGI's free public CUSIP->ticker mapping API,
queried directly (not via SEC's own optional FIGI column - an earlier version of
this module tried that shortcut and it was live-verified to undercount real
institutional shares by ~12x, since most 13F filers simply don't report FIGI at
all - see the module's own docstring for the full story).
"""

import json

import pytest

from utils.external.openfigi_crosswalk import EntityNameIndex, fetch_cusip_tickers, names_plausibly_match


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_fetch_cusip_tickers_parses_resolved_cusips(monkeypatch):
    payload = [
        {"data": [{"ticker": "AAPL", "name": "APPLE INC", "compositeFIGI": "BBG000B9XRY4"}]},
    ]
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=30: _FakeResponse(payload))

    result = fetch_cusip_tickers(["037833100"])

    assert result == {"037833100": {"ticker": "AAPL", "name": "APPLE INC"}}


def test_fetch_cusip_tickers_prefers_us_listing_over_foreign_cross_listing(monkeypatch):
    """Live-verified via Agilent's real CUSIP (00846U101): OpenFIGI returns 100+ listings
    across every exchange the security trades on, not primary-listing-first - data[0] was a
    German Xetra listing ("AG8"), with the real US listing ("A") at index 8. Picking data[0]
    unconditionally resolved a real US large-cap to the wrong ticker."""
    payload = [
        {
            "data": [
                {"ticker": "AG8", "name": "AGILENT TECHNOLOGIES INC", "exchCode": "GR"},
                {"ticker": "AG8", "name": "AGILENT TECHNOLOGIES INC", "exchCode": "GF"},
                {"ticker": "A", "name": "AGILENT TECHNOLOGIES INC", "exchCode": "US"},
                {"ticker": "A", "name": "AGILENT TECHNOLOGIES INC", "exchCode": "UN"},
            ]
        },
    ]
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=30: _FakeResponse(payload))

    result = fetch_cusip_tickers(["00846U101"])

    assert result == {"00846U101": {"ticker": "A", "name": "AGILENT TECHNOLOGIES INC"}}


def test_fetch_cusip_tickers_falls_back_to_first_listing_when_no_us_exchange(monkeypatch):
    """A genuinely foreign-only security (no US listing at all) must keep resolving to its
    only available listing, not be dropped just because it lacks an exchCode "US" entry."""
    payload = [
        {"data": [{"ticker": "VOD", "name": "VODAFONE GROUP PLC", "exchCode": "LN"}]},
    ]
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=30: _FakeResponse(payload))

    result = fetch_cusip_tickers(["92857W209"])

    assert result == {"92857W209": {"ticker": "VOD", "name": "VODAFONE GROUP PLC"}}


def test_fetch_cusip_tickers_skips_unresolved_cusips_without_fabricating(monkeypatch):
    """OpenFIGI returns an 'error' object (no 'data' key) for CUSIPs it can't map
    (bonds, private placements, foreign-only listings) - those must simply be
    absent from the result, never defaulted to something."""
    payload = [{"error": "No identifier found."}]
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=30: _FakeResponse(payload))

    result = fetch_cusip_tickers(["000000000"])

    assert result == {}


def test_fetch_cusip_tickers_raises_when_totally_unreachable(monkeypatch):
    """A resolved-zero-CUSIPs outcome is legitimate (see test above); every single
    request failing (network down, API contract changed) is a different, fatal
    condition and must raise so it isn't silently mistaken for 'no coverage'."""

    def _boom(req, timeout=30):
        raise OSError("network unreachable")

    monkeypatch.setattr("urllib.request.urlopen", _boom)

    with pytest.raises(RuntimeError, match="unreachable"):
        fetch_cusip_tickers(["037833100", "594918104"])


def test_fetch_cusip_tickers_batches_requests(monkeypatch):
    """More than 10 CUSIPs must split into multiple batched requests (OpenFIGI's
    unauthenticated per-request job limit - confirmed live: it 413s above 10)."""
    calls = []

    def _fake_urlopen(req, timeout=30):
        jobs = json.loads(req.data.decode("utf-8"))
        calls.append(len(jobs))
        return _FakeResponse([{"data": []} for _ in jobs])

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda *_: None)

    cusips = [f"{i:09d}" for i in range(25)]
    fetch_cusip_tickers(cusips)

    assert calls == [10, 10, 5]


def test_fetch_cusip_tickers_calls_on_batch_resolved_incrementally(monkeypatch):
    """FIXED 2026-07-27: callers used to only get results after the ENTIRE backlog was
    attempted - fatal for a ~34k-CUSIP cold start, since the process gets killed by its
    ECS task timeout long before that (see loaders/load_institutional_holdings_13f.py's
    _OPENFIGI_CROSSWALK_TIME_BUDGET_SEC). on_batch_resolved must fire after every batch
    so the caller can persist progress incrementally, not just at the very end."""

    def _fake_urlopen(req, timeout=30):
        jobs = json.loads(req.data.decode("utf-8"))
        return _FakeResponse([{"data": [{"ticker": f"T{j['idValue']}", "name": "X"}]} for j in jobs])

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda *_: None)

    seen_batches = []
    cusips = [f"{i:09d}" for i in range(25)]  # 3 batches: 10, 10, 5
    fetch_cusip_tickers(cusips, on_batch_resolved=seen_batches.append)

    assert len(seen_batches) == 3
    assert sum(len(b) for b in seen_batches) == 25
    # every CUSIP resolved in this fake response - each batch's entries are non-None
    assert all(v is not None for batch in seen_batches for v in batch.values())


def test_fetch_cusip_tickers_stops_at_deadline_and_returns_partial(monkeypatch):
    """A deadline reached mid-backlog must stop starting new batches and return whatever
    was resolved so far, instead of continuing to grind toward a kill it can't avoid."""
    import time as time_module

    def _fake_urlopen(req, timeout=30):
        jobs = json.loads(req.data.decode("utf-8"))
        return _FakeResponse([{"data": [{"ticker": f"T{j['idValue']}", "name": "X"}]} for j in jobs])

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda *_: None)

    # 5 batches worth of CUSIPs, but the deadline is already in the past - only the
    # first iteration's deadline check should stop everything before any batch runs.
    cusips = [f"{i:09d}" for i in range(50)]
    result = fetch_cusip_tickers(cusips, deadline=time_module.monotonic() - 1)

    assert result == {}


def test_fetch_cusip_tickers_deadline_hit_does_not_raise_even_if_zero_succeeded(monkeypatch):
    """A deadline cutting the run short before any batch succeeds is a time-budget
    outcome, not the 'OpenFIGI is unreachable' failure mode - must not raise."""
    import time as time_module

    def _boom(req, timeout=30):
        raise OSError("network unreachable")

    monkeypatch.setattr("urllib.request.urlopen", _boom)

    result = fetch_cusip_tickers(["037833100"], deadline=time_module.monotonic() - 1)
    assert result == {}


def test_fetch_cusip_tickers_discards_batch_on_response_length_mismatch(monkeypatch):
    """OpenFIGI's contract is positional (result[i] answers job[i] in the same
    order) - fetch_cusip_tickers relies on that to zip cusips to results. If a
    response ever comes back a different length than the request (truncated
    response, API contract change), zip() would silently pair each cusip with
    the WRONG result. The whole batch must be discarded instead of risking a
    fabricated/misaligned mapping - and with only one batch ever succeeding
    (zero here), the overall call must still raise as fully unreachable."""

    def _fake_urlopen(req, timeout=30):
        jobs = json.loads(req.data.decode("utf-8"))
        # Request 2 CUSIPs, respond with only 1 result.
        return _FakeResponse([{"data": [{"ticker": f"T{jobs[0]['idValue']}", "name": "X"}]}])

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda *_: None)

    with pytest.raises(RuntimeError, match="unreachable"):
        fetch_cusip_tickers(["037833100", "594918104"])


def test_names_plausibly_match_positive_case():
    assert names_plausibly_match("APPLE INC", "Apple Inc.") is True


def test_names_plausibly_match_handles_punctuation_as_a_separator_not_noise():
    """Live-verified false negative this exact case caused before the fix:
    OpenFIGI's 'AMAZON.COM INC' must match SEC's own space-separated
    'AMAZON COM INC' entity_name - naively deleting the period merges
    'AMAZON.COM' into one 'AMAZONCOM' token that never matches."""
    assert names_plausibly_match("AMAZON.COM INC", "AMAZON COM INC") is True


def test_names_plausibly_match_rejects_the_live_verified_xom_mismatch():
    """OpenFIGI resolves ticker XOM to 'EXXONMOBIL HOLDINGS CORP', a different
    entity than the real 10-K filer 'EXXON MOBIL CORP' - live-verified 2026-07-27.
    This is the safety net that catches a wrong-entity CUSIP/ticker resolution."""
    assert names_plausibly_match("EXXONMOBIL HOLDINGS CORP", "EXXON MOBIL CORP") is False


def test_names_plausibly_match_handles_missing_names():
    assert names_plausibly_match(None, "Apple Inc.") is False
    assert names_plausibly_match("APPLE INC", None) is False


def test_names_plausibly_match_strips_apostrophes_from_possessive_names():
    """FIXED 2026-08-18 (goal session, institutional ownership audit): a possessive
    entity name like SEC's "BRINK'S CO/THE" tokenized the apostrophe-attached word
    as "BRINK'S", which never equals OpenFIGI's non-possessive "BRINKS" - a false
    "wrong entity" rejection of a correct CUSIP resolution. Live-confirmed on 8 real
    tracked symbols including MCD (McDonald's) and LOW (Lowe's), both falling back
    to institutional_ownership_pct=NULL purely because of this apostrophe mismatch."""
    assert names_plausibly_match("BRINKS CO", "BRINK'S CO/THE") is True
    assert names_plausibly_match("MCDONALDS CORP", "MCDONALD'S CORP") is True
    assert names_plausibly_match("LOWES COMPANIES INC", "LOWE'S COS INC") is True


class TestEntityNameIndex:
    """FIXED 2026-08-18 (goal session, institutional ownership audit): OpenFIGI's
    ticker field for a CUSIP is sometimes wrong even when resolved_name is right -
    live-verified two ways. (1) Exxon Mobil's real CUSIP resolves to ticker "EXMOC"
    (not "XOM"), which isn't in our tracked universe at all, so the old code gave up
    before ever checking the name. (2) Verizon's real CUSIP resolves to ticker "BAC"
    (Bank of America's real ticker) - passes the "ticker is in our universe" check
    but names_plausibly_match correctly rejects it, and the old code had no fallback,
    silently discarding Verizon's own real 13F data. EntityNameIndex recovers both by
    searching our own tracked universe's names for an unambiguous match instead of
    trusting the crosswalk's ticker field."""

    def test_resolves_a_ticker_not_in_the_tracked_universe_via_name(self):
        index = EntityNameIndex({"XOM": "EXXON MOBIL CORP", "CVX": "CHEVRON CORP"})
        assert index.find("EXXON MOBIL CORP") == "XOM"

    def test_resolves_a_ticker_that_collides_with_a_different_tracked_symbol(self):
        """The crosswalk's ticker field says "BAC" but the resolved_name is
        Verizon's - the index must find VZ by name, not trust the wrong ticker."""
        index = EntityNameIndex({"BAC": "BANK OF AMERICA CORP", "VZ": "VERIZON COMMUNICATIONS INC"})
        assert index.find("VERIZON COMMUNICATIONS INC") == "VZ"

    def test_tolerates_the_same_naming_variants_as_names_plausibly_match(self):
        """The reverse lookup must accept the same real-world name variance
        (punctuation, possessives) already handled on the forward direction."""
        index = EntityNameIndex({"MCD": "MCDONALDS CORP", "LOW": "LOWES COMPANIES INC"})
        assert index.find("MCDONALD'S CORP") == "MCD"
        assert index.find("AMAZON.COM INC") is None  # not in this index at all

    def test_returns_none_when_no_tracked_symbol_matches(self):
        index = EntityNameIndex({"XOM": "EXXON MOBIL CORP"})
        assert index.find("SOME UNRELATED COMPANY INC") is None

    def test_returns_none_on_missing_or_empty_name(self):
        index = EntityNameIndex({"XOM": "EXXON MOBIL CORP"})
        assert index.find(None) is None
        assert index.find("") is None

    def test_returns_none_when_ambiguous_between_two_tracked_symbols(self):
        """Never guess: if resolved_name plausibly matches more than one tracked
        symbol's name, the same wrong-entity risk this module exists to prevent
        applies in reverse too - refuse rather than pick one."""
        index = EntityNameIndex(
            {
                "AAA": "GLOBAL HOLDINGS GROUP INC",
                "BBB": "GLOBAL HOLDINGS GROUP LLC",
            }
        )
        assert index.find("GLOBAL HOLDINGS GROUP CORP") is None
