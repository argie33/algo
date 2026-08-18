"""Regression test (2026-08-18, missing factor inputs audit continued):
_calculate_and_cache_ownership only read shares_outstanding from company_info_sec,
which closed-end funds/trusts (EFT/Eaton Vance, BGT/BlackRock, BSTZ/BlackRock,
XFLT/XAI - live-confirmed via real DB rows) never populate (their DEI cover-page
shares_outstanding concept isn't tagged the way operating companies tag it), even
though sec_valuations already has a real, current share count for all of them.
These are exactly the CEF/trust population openfigi_crosswalk.py's abbreviation-
matching fix (same session) newly resolves via the CUSIP crosswalk - without this
fallback they'd immediately hit a second, unrelated "shares_outstanding_unavailable"
blocker instead of computing a real institutional ownership percentage.
"""

from datetime import date

from loaders.load_institutional_holdings_13f import InstitutionalHoldings13FLoader


def _make_loader() -> InstitutionalHoldings13FLoader:
    return InstitutionalHoldings13FLoader.__new__(InstitutionalHoldings13FLoader)


class _FakeCursor:
    """Single-query stand-in: the real code now issues one COALESCE query per ticker,
    not two separate lookups - route by the ticker bound as a parameter."""

    def __init__(self, shares_by_ticker: dict[str, float | None]) -> None:
        self._shares_by_ticker = shares_by_ticker
        self._pending: tuple | None = None

    def execute(self, query: str, params=None) -> None:
        assert "COALESCE" in query, "expected the combined company_info_sec/sec_valuations fallback query"
        ticker = params[0]
        value = self._shares_by_ticker.get(ticker)
        self._pending = (value,)

    def fetchone(self):
        return self._pending


class _FakeDatabaseContext:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor

    def __enter__(self):
        return self._cursor

    def __exit__(self, *a):
        return False


def test_falls_back_to_sec_valuations_when_company_info_sec_shares_outstanding_is_null(monkeypatch):
    loader = _make_loader()
    # None here simulates company_info_sec being NULL, real sec_valuations value used instead
    # (COALESCE picks whichever the fake cursor returns - see _FakeCursor).
    cursor = _FakeCursor(shares_by_ticker={"EFT": 26_529_584.0})
    monkeypatch.setattr(
        "loaders.load_institutional_holdings_13f.DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(cursor)
    )
    monkeypatch.setattr("loaders.load_institutional_holdings_13f.get_active_symbols", lambda exclude_etfs=True: [])

    records = loader._calculate_and_cache_ownership(
        holdings_by_ticker={"EFT": 5_000_000},
        filing_date=date(2026, 5, 31),
    )

    assert len(records) == 1
    record = records[0]
    assert record["symbol"] == "EFT"
    assert record["data_unavailable"] is False
    assert record["reason"] is None
    assert record["institutional_ownership_pct"] == round((5_000_000 / 26_529_584.0) * 100, 2)


def test_stays_unavailable_when_neither_table_has_shares_outstanding(monkeypatch):
    loader = _make_loader()
    cursor = _FakeCursor(shares_by_ticker={"NODATACO": None})
    monkeypatch.setattr(
        "loaders.load_institutional_holdings_13f.DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(cursor)
    )
    monkeypatch.setattr("loaders.load_institutional_holdings_13f.get_active_symbols", lambda exclude_etfs=True: [])

    records = loader._calculate_and_cache_ownership(
        holdings_by_ticker={"NODATACO": 5_000_000},
        filing_date=date(2026, 5, 31),
    )

    assert len(records) == 1
    record = records[0]
    assert record["data_unavailable"] is True
    assert record["reason"] == "shares_outstanding_unavailable"
