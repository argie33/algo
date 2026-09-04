"""Regression test for the 2026-09-03 fix: get_active_symbols(exclude_etfs=True) and
lambda/api/routes/scores.py's mirrored _NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE must
exclude Business Development Companies whose SEC entity_type is 'operating' despite
sic_code=NULL.

Bug (confirmed live 2026-09-03): the 2026-08-20 sic_code/entity_type exclusion only catches
entity_type IN ('other', 'investment'), but SEC EDGAR classifies many real, registered BDCs
(Main Street Capital, Hercules Capital, FS KKR, Blue Owl, Goldman Sachs BDC, ...) as
entity_type='operating' despite also carrying sic_code=NULL - live-confirmed 31 active-universe
symbols match that signature, 30 of them genuine BDCs. These fund-of-loans entities have no
normal operating income statement and structurally can't report interest_coverage/total_debt/
free_cash_flow/etc. the way an operating company does, so they were still being scored (and
counted as real "Missing SEC/XBRL data" gaps) despite being the same non-operating-company
population the sic_code/entity_type check exists to remove.
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


def test_exclude_etfs_query_excludes_known_bdc_symbols(monkeypatch) -> None:
    _reset_cache()
    fake_ctx = _FakeDatabaseContext()
    monkeypatch.setattr(helpers_module, "DatabaseContext", fake_ctx)

    get_active_symbols(exclude_etfs=True)

    sql = fake_ctx._cursor.last_sql
    assert sql is not None
    for symbol in ("MAIN", "HTGC", "FSK", "GSBD", "OBDC"):
        assert symbol in sql
    _reset_cache()


def test_known_bdc_list_excludes_confirmed_false_positives() -> None:
    # CBC (Central Bancompany, a real bank holding company) and AFCG (Advanced Flower
    # Capital, a commercial mortgage REIT, not a registered BDC) share the sic_code=NULL/
    # entity_type='operating' signature but are NOT BDCs - see the module-level comment on
    # _KNOWN_BDC_ENTITY_TYPE_OPERATING_SYMBOLS for the live evidence.
    assert "CBC" not in _KNOWN_BDC_ENTITY_TYPE_OPERATING_SYMBOLS
    assert "AFCG" not in _KNOWN_BDC_ENTITY_TYPE_OPERATING_SYMBOLS


def test_scores_coverage_active_join_mirrors_bdc_exclusion() -> None:
    import importlib

    scores_mod = importlib.import_module("lambda.api.routes.scores")

    sql = scores_mod._NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE
    for symbol in sorted(_KNOWN_BDC_ENTITY_TYPE_OPERATING_SYMBOLS):
        assert symbol in sql, f"{symbol} missing from scores.py's mirrored BDC exclusion list"
