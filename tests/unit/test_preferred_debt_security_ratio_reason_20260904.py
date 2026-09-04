"""Regression test: pe_ratio/pb_ratio/ps_ratio_unavailable_reason must recognize a
preferred-stock/subordinated-debenture ticker (AFGB, DTB, DUKB, ...) instead of falling
through to generic "missing_sec_data".

Found live 2026-09-04 (goal session: "under 6k the right way" sweep). These child tickers
share their parent company's CIK, so annual_income_statement/annual_balance_sheet carries the
PARENT's real net_income/earnings_per_share/stockholders_equity - e.g. DUKB (Duke Energy's
5.625% Junior Subordinated Debentures) live-confirmed with FY2025 net_income=$4.968B,
earnings_per_share=$6.31, both belonging to Duke Energy's common stock, not the debenture
itself - while sec_valuations has zero row for the ticker at all (no market-equity computation
was ever attempted). A P/E, P/B, or P/S computed from the debenture's own price against its
parent's common-equity figures would be actively wrong, not just missing - see
loaders/helpers/sec_base.py's _get_preferred_or_debt_security_symbols() docstring (added in
loaders/load_value_quality_growth_metrics.py) for the full root-cause writeup.
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class _FakeSecValRow:
    """Minimal stand-in for a psycopg2 DictRow: supports sec_val_row[2] (data_unavailable flag,
    positional) and dict(sec_val_row) (mapping protocol) simultaneously."""

    def __init__(self, mapping):
        self._mapping = mapping

    def __getitem__(self, key):
        if key == 2:
            return False
        return self._mapping[key]

    def keys(self):
        return self._mapping.keys()


class _RecordingCursor:
    """Every windowed/anchor gate returns empty except the preferred/debt-security lookup,
    which returns `preferred_symbols` whenever the query targets stock_symbols.security_name."""

    def __init__(self, preferred_symbols):
        self._preferred_symbols = preferred_symbols
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchone(self):
        return None

    def fetchall(self):
        q = self._last_query
        if "stock_symbols" in q and "security_name" in q and "Subordinated" in q:
            return [(s,) for s in self._preferred_symbols]
        return []


def _run(monkeypatch, symbol, preferred_symbols=frozenset(), **sec_val_fields):
    import loaders.load_value_quality_growth_metrics as mod

    cursor = _RecordingCursor(preferred_symbols)

    class _FakeDatabaseContext:
        def __enter__(self):
            return cursor

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    loader = _make_loader()
    with patch.object(loader, "_get_analyst_forward_eps", return_value=None):
        return loader._build_value_metrics(symbol, _FakeSecValRow(sec_val_fields))


_BASE_FIELDS = {
    "pe_ratio": None,
    "pb_ratio": None,
    "ps_ratio": None,
    "ev_revenue": 12.0,
    "ev_ebitda": 12.0,
    "ebitda": 5_000_000.0,
    "enterprise_value": 200_000_000.0,
    "market_cap": 180_000_000.0,
    "total_debt": 30_000_000.0,
    "total_cash": 10_000_000.0,
    "fcf_yield": 6.0,
}


class TestPreferredOrDebtSecurityRatioReason:
    def test_preferred_ticker_gets_specific_reason(self, monkeypatch):
        result = _run(
            monkeypatch,
            "DUKB",
            preferred_symbols=frozenset({"DUKB"}),
            **_BASE_FIELDS,
        )

        assert result["pe_ratio_unavailable_reason"] == "preferred_or_debt_security_no_common_equity_ratio"
        assert result["pb_ratio_unavailable_reason"] == "preferred_or_debt_security_no_common_equity_ratio"
        assert result["ps_ratio_unavailable_reason"] == "preferred_or_debt_security_no_common_equity_ratio"

    def test_ordinary_symbol_keeps_generic_reason(self, monkeypatch):
        result = _run(
            monkeypatch,
            "ORDINARY",
            preferred_symbols=frozenset(),
            **_BASE_FIELDS,
        )

        assert result["pe_ratio_unavailable_reason"] != "preferred_or_debt_security_no_common_equity_ratio"
        assert result["pb_ratio_unavailable_reason"] != "preferred_or_debt_security_no_common_equity_ratio"
        assert result["ps_ratio_unavailable_reason"] != "preferred_or_debt_security_no_common_equity_ratio"
