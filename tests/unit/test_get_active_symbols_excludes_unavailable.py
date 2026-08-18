"""Regression test for the 2026-08-03 fix: get_active_symbols() must exclude
symbols permanently marked data_unavailable=true.

Bug (confirmed live 2026-08-03): both SQL branches in get_active_symbols()
selected `WHERE active = true` without excluding `data_unavailable = true`.
Once a symbol is marked permanently unavailable (confirmed delisted/no-data
via a 30-day yfinance lookback - see _mark_symbol_permanently_unavailable in
loaders/load_prices.py), it stays active=true forever and kept being pulled
into every loader run's expected-symbols count while never being able to post
a new row - a permanent ceiling on completion_pct that no retry could fix.
"""

import utils.loaders.helpers as helpers_module
from utils.loaders.helpers import get_active_symbols


class _FakeCursor:
    def __init__(self, rows: list[tuple[str]]) -> None:
        self._rows = rows
        self.last_sql: str | None = None

    def execute(self, sql: str, params: object = None) -> None:
        self.last_sql = sql

    def fetchall(self) -> list[tuple[str]]:
        return self._rows


class _FakeDatabaseContext:
    def __init__(self, rows: list[tuple[str]]) -> None:
        self._cursor = _FakeCursor(rows)

    def __call__(self, role: str) -> "_FakeDatabaseContext":
        return self

    def __enter__(self) -> _FakeCursor:
        return self._cursor

    def __exit__(self, *exc: object) -> None:
        return None


def _reset_cache() -> None:
    helpers_module._symbols_cache.clear()


def test_include_etfs_query_excludes_data_unavailable(monkeypatch) -> None:
    _reset_cache()
    fake_ctx = _FakeDatabaseContext(rows=[("AAPL",)])
    monkeypatch.setattr(helpers_module, "DatabaseContext", fake_ctx)

    get_active_symbols(exclude_etfs=False)

    sql = fake_ctx._cursor.last_sql
    assert sql is not None
    assert "data_unavailable" in sql
    _reset_cache()


def test_exclude_etfs_query_excludes_data_unavailable(monkeypatch) -> None:
    _reset_cache()
    fake_ctx = _FakeDatabaseContext(rows=[("AAPL",)])
    monkeypatch.setattr(helpers_module, "DatabaseContext", fake_ctx)

    get_active_symbols(exclude_etfs=True)

    sql = fake_ctx._cursor.last_sql
    assert sql is not None
    assert "data_unavailable" in sql
    _reset_cache()


def test_exclude_etfs_query_filters_on_etf_column(monkeypatch) -> None:
    """Regression test for the 2026-08-18 fix (goal: "no SEC data"/loader audit),
    superseding the 2026-08-03 test this replaces.

    The 2026-08-03 premise - that stock_symbols.etf never holds anything but 'N', so
    checking it is dead weight - is disproven by live data: 5 stock_symbols rows (SPY,
    QQQ, IWM, AGG, EFA - major, heavily-followed ETFs) have etf='true', not 'N' or NULL.
    None of their names match the security_name regex below (e.g. "SPDR S&P 500 ETF
    Trust"), so with no etf-column check they passed straight through
    get_active_symbols(exclude_etfs=True) and generated spurious missing_sec_data/
    no-filing rows in loaders that need real stocks only - symbols that structurally
    never file 10-Ks/Form 4s/13Fs. Re-added as defense-in-depth rather than extending the
    regex - "Trust"/"Fund" are too generic and would false-positive-exclude real
    operating companies (e.g. "Digital Realty Trust").
    """
    _reset_cache()
    fake_ctx = _FakeDatabaseContext(rows=[("AAPL",)])
    monkeypatch.setattr(helpers_module, "DatabaseContext", fake_ctx)

    get_active_symbols(exclude_etfs=True)

    sql = fake_ctx._cursor.last_sql
    assert sql is not None
    assert "etf" in sql
    assert "'true'" in sql
    _reset_cache()
