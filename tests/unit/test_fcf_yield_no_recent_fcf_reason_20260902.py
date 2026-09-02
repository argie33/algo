"""Regression test: value_metrics.fcf_yield_unavailable_reason must distinguish a filer with
genuinely no free cash flow reported in its 3 most recent fiscal years from a real SEC
extraction gap, reusing the same _get_no_recent_free_cash_flow_symbols() gate already wired
into quality_metrics.free_cash_flow_unavailable_reason (test_free_cash_flow_reason_gate_20260902.py).

Found live 2026-09-02: sec_valuations derives fcf as ocf - capex - sbc (with a cross-year
avg_fcf_fallback), the same underlying "does this filer report free cash flow at all" business
fact the quality_metrics gate already identifies - but value_metrics.fcf_yield_unavailable_reason
was still a bare "missing_sec_data" if fcf_yield is None. Live-confirmed 207 of 421 (49%)
universe fcf_yield "missing_sec_data" rows are this exact case.
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
    def __init__(self, no_recent_fcf_symbols):
        self._no_recent_fcf = no_recent_fcf_symbols
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchone(self):
        return None

    def fetchall(self):
        if "annual_cash_flow" in self._last_query and "COUNT(free_cash_flow)" in self._last_query:
            return [(s,) for s in self._no_recent_fcf]
        return []


def _run(monkeypatch, no_recent_fcf_symbols=frozenset(), **sec_val_fields):
    import loaders.load_value_quality_growth_metrics as mod

    cursor = _RecordingCursor(no_recent_fcf_symbols)

    class _FakeDatabaseContext:
        def __enter__(self):
            return cursor

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    loader = _make_loader()
    with patch.object(loader, "_get_analyst_forward_eps", return_value=None):
        return loader._build_value_metrics("NOFCF", _FakeSecValRow(sec_val_fields))


class TestFcfYieldNoRecentFcfReason:
    def test_fcf_yield_propagates_no_recent_fcf_reason(self, monkeypatch):
        result = _run(
            monkeypatch,
            no_recent_fcf_symbols=frozenset({"NOFCF"}),
            pe_ratio=15.0,
            pb_ratio=2.0,
            ps_ratio=3.0,
            fcf_yield=None,
            enterprise_value=1_000_000_000.0,
            market_cap=1_100_000_000.0,
        )

        assert result["fcf_yield_unavailable_reason"] == "no_recent_free_cash_flow_reported"

    def test_symbol_not_in_gate_keeps_generic_reason(self, monkeypatch):
        result = _run(
            monkeypatch,
            no_recent_fcf_symbols=frozenset(),
            pe_ratio=15.0,
            pb_ratio=2.0,
            ps_ratio=3.0,
            fcf_yield=None,
            enterprise_value=1_000_000_000.0,
            market_cap=1_100_000_000.0,
        )

        assert result["fcf_yield_unavailable_reason"] == "missing_sec_data"

    def test_real_fcf_yield_still_populates_with_no_reason(self, monkeypatch):
        result = _run(
            monkeypatch,
            no_recent_fcf_symbols=frozenset({"NOFCF"}),
            pe_ratio=15.0,
            pb_ratio=2.0,
            ps_ratio=3.0,
            fcf_yield=6.5,
            enterprise_value=1_000_000_000.0,
            market_cap=1_100_000_000.0,
        )

        assert result["fcf_yield"] == 6.5
        assert result.get("fcf_yield_unavailable_reason") is None
