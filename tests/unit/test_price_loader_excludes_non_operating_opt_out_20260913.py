"""Regression test for the 2026-09-13 fix: get_active_symbols(exclude_etfs=True,
exclude_non_operating=False) must NOT apply the fund/BDC/financing-trust exclusion clause.

Bug (confirmed live 2026-09-13): load_prices.py passed exclude_etfs=True (added 2026-07-13
to stop double-loading ~5,250 real ETFs) and silently inherited the sic_code/entity_type
fund-exclusion clause once that was bundled into the same exclude_etfs=True branch on
2026-08-20/2026-09-03. That clause is correct for financial-statement loaders (funds/BDCs
can't report normal operating financials) but wrong for price/technical loaders - live-
confirmed 154 real, actively-traded CEFs/BDCs (BBN, BST, MAIN, FSK, GAB, HQH, ...) silently
stopped getting ANY price_daily updates the moment their classification matched.
"""

import utils.loaders.helpers as helpers_module
from utils.loaders.helpers import _KNOWN_BDC_ENTITY_TYPE_OPERATING_SYMBOLS, get_active_symbols


class _FakeCursor:
    def __init__(self) -> None:
        self.last_sql: str | None = None

    def execute(self, sql: str, params: object = None) -> None:
        self.last_sql = sql

    def fetchall(self) -> list[tuple[str]]:
        return [("AAPL",)]


class _FakeDatabaseContext:
    def __init__(self) -> None:
        self._cursor = _FakeCursor()

    def __call__(self, role: str) -> "_FakeDatabaseContext":
        return self

    def __enter__(self) -> _FakeCursor:
        return self._cursor

    def __exit__(self, *exc: object) -> None:
        return None


def _reset_cache() -> None:
    helpers_module._symbols_cache.clear()


def test_exclude_non_operating_false_omits_bdc_denylist(monkeypatch) -> None:
    _reset_cache()
    fake_ctx = _FakeDatabaseContext()
    monkeypatch.setattr(helpers_module, "DatabaseContext", fake_ctx)

    get_active_symbols(exclude_etfs=True, exclude_non_operating=False)

    sql = fake_ctx._cursor.last_sql
    assert sql is not None
    # None of the known BDC symbols should appear as an exclusion in this SQL - price
    # loaders need these real, tradable securities.
    for symbol in sorted(_KNOWN_BDC_ENTITY_TYPE_OPERATING_SYMBOLS):
        assert symbol not in sql, f"{symbol} should not be excluded when exclude_non_operating=False"
    assert "NOT IN ('TVC'" not in sql
    assert "COALESCE(c.sic_code" not in sql
    # Real-ETF and warrant/rights/SPAC exclusions must still apply.
    assert "etf != 'true'" in sql
    assert "Warrant" in sql
    _reset_cache()


def test_exclude_non_operating_defaults_to_exclude_etfs_value(monkeypatch) -> None:
    _reset_cache()
    fake_ctx = _FakeDatabaseContext()
    monkeypatch.setattr(helpers_module, "DatabaseContext", fake_ctx)

    # Omitting exclude_non_operating with exclude_etfs=True must preserve prior behavior
    # for the ~19 existing financial-statement-loader callers.
    get_active_symbols(exclude_etfs=True)

    sql = fake_ctx._cursor.last_sql
    assert sql is not None
    assert "MAIN" in sql
    assert "sic_code" in sql
    _reset_cache()
