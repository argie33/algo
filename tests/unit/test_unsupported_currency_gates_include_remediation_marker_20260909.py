"""Regression test (2026-09-09, goal: SEC/XBRL missing-data reduction, "under 500" push):
_get_unsupported_currency_ocf_symbols()/_get_unsupported_currency_balance_sheet_symbols() in
loaders/helpers/vqg_symbol_gates.py only matched the live per-fetch guard's own
"unsupported_currency_no_fx_rate" reason, missing the 8-9 symbols (BAK/EDN/GGAL/HEPS/SUPV/
TEO/TGS/TKC/TV) migration 1250 (null_stale_raw_currency_financial_statements) nulled out and
marked "raw_unconverted_currency_stale_value_20260829" instead - a one-off remediation for
pre-guard rows that had already stored the same unconvertible raw local-currency figure. Both
reasons mean the identical thing (an FPI's statement figures are only tagged in a
hyperinflationary/unsupported currency, not a real loader gap), so both gates must recognize
either reason string.
"""

from loaders.helpers.vqg_symbol_gates import SymbolGateMixin


class _FakeCursor:
    def __init__(self):
        self.last_query = None

    def execute(self, query, params=None):
        self.last_query = query

    def fetchall(self):
        return [("GGAL",), ("BAK",)]


class _FakeDatabaseContext:
    def __init__(self, cursor):
        self._cursor = cursor

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return self._cursor

    def __exit__(self, *exc):
        return False


def _make_gates_host(monkeypatch, cursor):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(cursor))
    host = SymbolGateMixin.__new__(SymbolGateMixin)
    return host


class TestUnsupportedCurrencyGatesIncludeRemediationMarker:
    def test_ocf_gate_query_includes_both_reasons(self, monkeypatch):
        cursor = _FakeCursor()
        host = _make_gates_host(monkeypatch, cursor)

        result = host._get_unsupported_currency_ocf_symbols()

        assert "unsupported_currency_no_fx_rate" in cursor.last_query
        assert "raw_unconverted_currency_stale_value_20260829" in cursor.last_query
        assert result == frozenset({"GGAL", "BAK"})

    def test_balance_sheet_gate_query_includes_both_reasons(self, monkeypatch):
        cursor = _FakeCursor()
        host = _make_gates_host(monkeypatch, cursor)

        result = host._get_unsupported_currency_balance_sheet_symbols()

        assert "unsupported_currency_no_fx_rate" in cursor.last_query
        assert "raw_unconverted_currency_stale_value_20260829" in cursor.last_query
        assert result == frozenset({"GGAL", "BAK"})
