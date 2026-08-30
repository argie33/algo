"""Regression test (2026-08-29, goal: "full data" audit continuation):
_calculate_and_cache_ownership() previously tagged EVERY active symbol absent from
holdings_by_ticker with the same "no_resolved_13f_holdings" marker
(data_unavailable=True), whether its CUSIP was genuinely unresolvable OR it was resolvable
but simply had zero institutional shares reported for it in the current quarter's bulk
dataset - a real, current fact, not a data gap. See
[[institutional_holdings_13f_crosswalk_resolved_but_reason_unclear_investigated_20260829]]
for the investigation that found 33 live symbols mislabeled this way.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from loaders.load_institutional_holdings_13f import InstitutionalHoldings13FLoader


def _make_loader() -> InstitutionalHoldings13FLoader:
    return InstitutionalHoldings13FLoader.__new__(InstitutionalHoldings13FLoader)


class _FakeCursor:
    """Routes FPI lookup (no rows) and shares_outstanding COALESCE lookups (real value
    for RESOLVED_HOLDER, so it hits the success branch and lands in resolved_tickers)."""

    def execute(self, query, params=None):
        self._query = query
        if "is_foreign_private_issuer" in query:
            self._rows = []
        elif "COALESCE" in query:
            ticker = params[0]
            self._rows = [(50_000_000.0 if ticker == "RESOLVED_HOLDER" else None,)]
        else:
            self._rows = []

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeDatabaseContext:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self._cursor

    def __exit__(self, *a):
        return False


def test_resolvable_symbol_with_zero_current_holdings_gets_real_zero_not_unavailable(monkeypatch):
    loader = _make_loader()
    cursor = _FakeCursor()
    monkeypatch.setattr(
        "loaders.load_institutional_holdings_13f.DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(cursor)
    )
    monkeypatch.setattr(
        "loaders.load_institutional_holdings_13f.get_active_symbols",
        lambda exclude_etfs=True: ["RESOLVED_HOLDER", "RESOLVABLE_ZERO", "GENUINELY_UNRESOLVABLE"],
    )
    loader._get_crosswalk_resolvable_tickers = MagicMock(return_value={"RESOLVED_HOLDER", "RESOLVABLE_ZERO"})

    records = loader._calculate_and_cache_ownership(
        holdings_by_ticker={"RESOLVED_HOLDER": 5_000_000},
        filing_date=date(2026, 5, 31),
    )

    by_symbol = {r["symbol"]: r for r in records}
    assert set(by_symbol) == {"RESOLVED_HOLDER", "RESOLVABLE_ZERO", "GENUINELY_UNRESOLVABLE"}

    # Resolvable, but zero shares reported this quarter: real 0%, not an unavailable marker.
    zero = by_symbol["RESOLVABLE_ZERO"]
    assert zero["data_unavailable"] is False
    assert zero["reason"] is None
    assert zero["institutional_ownership_pct"] == 0.0
    assert zero["number_of_institutional_holders"] == 0
    assert zero["data_source"] == "sec_form13f_bulk"

    # Genuinely unresolvable CUSIP: keeps the real "no_resolved_13f_holdings" gap marker.
    unresolvable = by_symbol["GENUINELY_UNRESOLVABLE"]
    assert unresolvable["data_unavailable"] is True
    assert unresolvable["reason"] == "no_resolved_13f_holdings"


class _CrosswalkFakeCursor:
    """Routes the two queries _get_crosswalk_resolvable_tickers issues: the crosswalk
    scan, and (only for tickers an exact match didn't cover) local entity names."""

    def __init__(self, crosswalk_rows, local_name_rows):
        self._crosswalk_rows = crosswalk_rows
        self._local_name_rows = local_name_rows

    def execute(self, query, params=None):
        self._query = query

    def fetchall(self):
        if "sec_13f_cusip_crosswalk" in self._query:
            return self._crosswalk_rows
        return self._local_name_rows


def test_exact_ticker_match_resolves_without_requiring_a_local_entity_name(monkeypatch):
    """Live-reproduced 2026-08-29: HIFS (Hingham Institution for Savings) has an exact
    `ticker='HIFS'` row in sec_13f_cusip_crosswalk, but company_info_sec.entity_name is
    NULL for it (a separate, already-documented small-bank gap) - a version of this check
    that required the full name-plausibility gate for EVERY row (not just fuzzy-rescue
    ones) was a complete no-op for this entire population (0/332 real symbols matched)."""
    loader = _make_loader()
    cursor = _CrosswalkFakeCursor(
        crosswalk_rows=[("433323102", "HIFS", "HINGHAM INSTITUTION FOR SVGS")],
        local_name_rows=[],
    )
    monkeypatch.setattr(
        "loaders.load_institutional_holdings_13f.DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(cursor)
    )
    monkeypatch.setattr(
        "loaders.load_institutional_holdings_13f.get_active_symbols", lambda exclude_etfs=True: ["HIFS"]
    )

    resolvable = loader._get_crosswalk_resolvable_tickers()

    assert resolvable == {"HIFS"}


def test_never_calls_resolvable_tickers_lookup_when_nothing_is_unresolved(monkeypatch):
    """Performance/test-isolation guard: the (real DB query) resolvable-tickers lookup
    should be skipped entirely when every active symbol already resolved."""
    loader = _make_loader()
    monkeypatch.setattr(
        "loaders.load_institutional_holdings_13f.DatabaseContext",
        lambda *a, **kw: _FakeDatabaseContext(_FakeCursor()),
    )
    monkeypatch.setattr(
        "loaders.load_institutional_holdings_13f.get_active_symbols",
        lambda exclude_etfs=True: ["RESOLVED_HOLDER"],
    )
    with patch.object(loader, "_get_crosswalk_resolvable_tickers") as mock_lookup:
        loader._calculate_and_cache_ownership(
            holdings_by_ticker={"RESOLVED_HOLDER": 5_000_000},
            filing_date=date(2026, 5, 31),
        )
    mock_lookup.assert_not_called()
