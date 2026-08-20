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


def test_exclude_etfs_query_joins_company_info_sec_for_fund_detection(monkeypatch) -> None:
    """Regression test for the 2026-08-20 fix (goal: "scores still including ETFs").

    Neither the etf column nor the security_name regex catch closed-end funds (CEFs), BDCs,
    or ETNs whose names don't contain a blocklisted word - e.g. ASA ("ASA Gold & Precious
    Metals Ltd"), BSTZ/FINS ("...Term Trust" - bare "Trust" is deliberately not blocklisted).
    Live-confirmed 88 such symbols had polluted stock_scores rows as of 2026-08-20. Fix:
    join company_info_sec and additionally exclude symbols with no real SIC classification
    (sic_code NULL/0) and a non-operating entity_type ('other'/'investment'), with an
    explicit carve-out for OZK (Bank OZK - the one confirmed false positive in the live
    universe, a real bank whose company_info_sec row happens to share this same profile).
    """
    _reset_cache()
    fake_ctx = _FakeDatabaseContext(rows=[("AAPL",)])
    monkeypatch.setattr(helpers_module, "DatabaseContext", fake_ctx)

    get_active_symbols(exclude_etfs=True)

    sql = fake_ctx._cursor.last_sql
    assert sql is not None
    assert "LEFT JOIN company_info_sec" in sql
    assert "c.sic_code" in sql
    assert "c.entity_type" in sql
    assert "'OZK'" in sql
    _reset_cache()


def test_exclude_etfs_query_uses_word_boundary_not_backspace(monkeypatch) -> None:
    """Regression test for the 2026-08-20 fix (goal: "scores still including ETFs").

    `\\b` in PostgreSQL's regex engine is a literal backspace character, not a word-boundary
    assertion - `\\y` is. The old `!~* '\\b(...)\\b'` clause was silently dead code: no
    security_name contains a real backspace byte, so the clause always evaluated true (no
    match), meaning every token in the list (Warrant/Unit/SPAC/Preferred/.../Bitcoin) never
    actually excluded anything. Also drops "Right" and "Bitcoin" from the blocklist -
    live-verified collision-prone against real operating companies once word-boundary
    matching actually works (AMX/RLX/WDH's ADS boilerplate "the right to receive...", and
    ABTC "American Bitcoin Corp.", a real bitcoin-mining operating company).
    """
    _reset_cache()
    fake_ctx = _FakeDatabaseContext(rows=[("AAPL",)])
    monkeypatch.setattr(helpers_module, "DatabaseContext", fake_ctx)

    get_active_symbols(exclude_etfs=True)

    sql = fake_ctx._cursor.last_sql
    assert sql is not None
    assert r"\y(" in sql
    assert r"\b(" not in sql
    assert "Right|" not in sql
    assert "|Bitcoin|" not in sql
    _reset_cache()
