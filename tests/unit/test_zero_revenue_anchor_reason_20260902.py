"""Regression test: ps_ratio/ev_revenue_unavailable_reason must distinguish a real $0.00
anchor-year revenue (load_sec_valuations.py's ttm_revenue is exactly this anchor row's
revenue) from the windowed "no revenue reported in any of the 3 most recent fiscal years"
case _get_no_recent_revenue_symbols() already covers, instead of falling through to generic
"missing_sec_data".

Found live 2026-09-02 (same /goal session as the negative_enterprise_value fix): a company
can have real revenue in prior years yet a genuine $0 anchor year (e.g. AREC: 2025 anchor
revenue=$0.00 despite $11.8M and $34K in the two prior years) - that year's EV/Revenue and
P/S are undefined regardless of other years' history. Live-confirmed ~40-47 of the
ev_revenue "missing_sec_data" residual population is this exact case.
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
    """Windowed no-recent-revenue gate (ROW_NUMBER()) always returns empty - only the
    zero-revenue-anchor sibling (DISTINCT ON, no ROW_NUMBER()) can fire in this test."""

    def __init__(self, zero_revenue_anchor_symbols):
        self._zero_revenue_anchor = zero_revenue_anchor_symbols
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchone(self):
        return None

    def fetchall(self):
        q = self._last_query
        if "ROW_NUMBER()" in q:
            return []
        if "annual_income_statement" in q and "DISTINCT ON" in q:
            return [(s,) for s in self._zero_revenue_anchor]
        return []


def _run(monkeypatch, zero_revenue_anchor_symbols=frozenset(), **sec_val_fields):
    import loaders.load_value_quality_growth_metrics as mod

    cursor = _RecordingCursor(zero_revenue_anchor_symbols)

    class _FakeDatabaseContext:
        def __enter__(self):
            return cursor

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    loader = _make_loader()
    with patch.object(loader, "_get_analyst_forward_eps", return_value=None):
        return loader._build_value_metrics("ZEROREV", _FakeSecValRow(sec_val_fields))


class TestZeroRevenueAnchorReason:
    def test_ev_revenue_gets_zero_revenue_reason(self, monkeypatch):
        result = _run(
            monkeypatch,
            zero_revenue_anchor_symbols=frozenset({"ZEROREV"}),
            pe_ratio=15.0,
            pb_ratio=2.0,
            ps_ratio=None,
            ev_revenue=None,
            ev_ebitda=12.0,
            ebitda=5_000_000.0,
            enterprise_value=200_000_000.0,
            market_cap=180_000_000.0,
            total_debt=30_000_000.0,
            total_cash=10_000_000.0,
            fcf_yield=6.0,
        )

        assert result["ev_revenue_unavailable_reason"] == "zero_revenue_reported_this_period"
        assert result["ps_ratio_unavailable_reason"] == "zero_revenue_reported_this_period"

    def test_symbol_not_in_gate_keeps_generic_reason(self, monkeypatch):
        result = _run(
            monkeypatch,
            zero_revenue_anchor_symbols=frozenset(),
            pe_ratio=15.0,
            pb_ratio=2.0,
            ps_ratio=None,
            ev_revenue=None,
            ev_ebitda=12.0,
            ebitda=5_000_000.0,
            enterprise_value=200_000_000.0,
            market_cap=180_000_000.0,
            total_debt=30_000_000.0,
            total_cash=10_000_000.0,
            fcf_yield=6.0,
        )

        assert result["ev_revenue_unavailable_reason"] == "missing_sec_data"
        assert result["ps_ratio_unavailable_reason"] == "missing_sec_data"
