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


def test_exclude_etfs_query_does_not_reference_nonexistent_etf_column(monkeypatch) -> None:
    """Regression test for the 2026-08-03 fix: stock_symbols.etf was never created by any
    migration or schema.sql, so the exclude_etfs=True branch's `(etf IS NULL OR etf = 'N')`
    clause raised UndefinedColumn unconditionally - live-confirmed against a real DB with
    active/data_unavailable already present. Also dead weight even where the column did
    exist: load_market_constituents.py diverts real ETFs into a separate etf_symbols table
    before any row reaches stock_symbols, hardcoding etf="N" for the rest - so the clause
    could only ever evaluate true.
    """
    _reset_cache()
    fake_ctx = _FakeDatabaseContext(rows=[("AAPL",)])
    monkeypatch.setattr(helpers_module, "DatabaseContext", fake_ctx)

    get_active_symbols(exclude_etfs=True)

    sql = fake_ctx._cursor.last_sql
    assert sql is not None
    assert "etf" not in sql
    _reset_cache()
