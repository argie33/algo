"""Regression test: ev_revenue/ev_ebitda_unavailable_reason must distinguish a filer with no
itemized debt components (long_term_debt/short_term_debt/operating_lease_liability/
finance_lease_liability all absent in its 3 most recent fiscal years) from a real SEC
extraction gap, reusing the same _get_no_recent_debt_components_symbols() gate already built
for quality_metrics.total_debt (test_debt_to_equity...).

Found live 2026-09-02: enterprise_value = market_cap + total_debt - total_cash, so it comes
back None whenever total_debt can't be itemized even when revenue/ebitda are both present and
usable - but ev_revenue/ev_ebitda_unavailable_reason only checked no_revenue_reported/
unprofitable_stock/ebitda_not_extracted before falling to generic "missing_sec_data". Live-
confirmed 56 of 291 (19%) universe ev_revenue and 28 of 83 (34%) universe ev_ebitda
missing_sec_data rows are this exact case.
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
    def __init__(self, no_recent_debt_symbols):
        self._no_recent_debt = no_recent_debt_symbols
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchone(self):
        return None

    def fetchall(self):
        if "annual_balance_sheet" in self._last_query and "long_term_debt" in self._last_query:
            return [(s,) for s in self._no_recent_debt]
        return []


def _run(monkeypatch, no_recent_debt_symbols=frozenset(), **sec_val_fields):
    import loaders.load_value_quality_growth_metrics as mod

    cursor = _RecordingCursor(no_recent_debt_symbols)

    class _FakeDatabaseContext:
        def __enter__(self):
            return cursor

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    loader = _make_loader()
    with patch.object(loader, "_get_analyst_forward_eps", return_value=None):
        return loader._build_value_metrics("NODEBT", _FakeSecValRow(sec_val_fields))


class TestEvRevenueEvEbitdaDebtNotItemizedReason:
    def test_ev_revenue_propagates_total_debt_not_itemized_reason(self, monkeypatch):
        result = _run(
            monkeypatch,
            no_recent_debt_symbols=frozenset({"NODEBT"}),
            pe_ratio=15.0,
            pb_ratio=2.0,
            ps_ratio=3.0,
            ev_revenue=None,
            ev_ebitda=None,
            ebitda=200_000_000.0,
            enterprise_value=None,
            market_cap=1_000_000_000.0,
            fcf_yield=6.0,
        )

        assert result["ev_revenue_unavailable_reason"] == "total_debt_not_itemized"
        assert result["ev_ebitda_unavailable_reason"] == "total_debt_not_itemized"

    def test_symbol_not_in_gate_keeps_generic_reason(self, monkeypatch):
        result = _run(
            monkeypatch,
            no_recent_debt_symbols=frozenset(),
            pe_ratio=15.0,
            pb_ratio=2.0,
            ps_ratio=3.0,
            ev_revenue=None,
            ev_ebitda=None,
            ebitda=200_000_000.0,
            enterprise_value=None,
            market_cap=1_000_000_000.0,
            fcf_yield=6.0,
        )

        assert result["ev_revenue_unavailable_reason"] == "missing_sec_data"
        assert result["ev_ebitda_unavailable_reason"] == "missing_sec_data"

    def test_real_ev_still_populates_with_no_reason(self, monkeypatch):
        result = _run(
            monkeypatch,
            no_recent_debt_symbols=frozenset({"NODEBT"}),
            pe_ratio=15.0,
            pb_ratio=2.0,
            ps_ratio=3.0,
            ev_revenue=8.2,
            ev_ebitda=12.0,
            ebitda=200_000_000.0,
            enterprise_value=2_400_000_000.0,
            market_cap=1_000_000_000.0,
            fcf_yield=6.0,
        )

        assert result["ev_revenue"] == 8.2
        assert result.get("ev_revenue_unavailable_reason") is None
        assert result["ev_ebitda"] == 12.0
        assert result.get("ev_ebitda_unavailable_reason") is None
