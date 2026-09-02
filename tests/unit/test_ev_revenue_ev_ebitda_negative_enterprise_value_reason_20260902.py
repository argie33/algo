"""Regression test: ev_revenue/ev_ebitda_unavailable_reason must distinguish a genuine
net-cash-rich filer (total_cash alone exceeds market_cap + total_debt, so
load_sec_valuations.py's own EV computation comes out <= 0 and never persists a value) from
a real SEC extraction gap, instead of falling through to generic "missing_sec_data".

Found live 2026-09-02 (same /goal session as the total_debt_not_itemized fix in
test_ev_revenue_ev_ebitda_debt_not_itemized_reason_20260902.py): live-confirmed 120 of 259
(46%) universe ev_revenue and 42 of 76 (55%) universe ev_ebitda "missing_sec_data" residual
rows are this exact case - EV/EBITDA and EV/Revenue are not meaningful ratios for a company
effectively worth less than its own cash pile, same "not applicable" class as
unprofitable_stock, not a data gap.
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
    def execute(self, query, params=None):
        pass

    def fetchone(self):
        return None

    def fetchall(self):
        return []


def _run(monkeypatch, **sec_val_fields):
    import loaders.load_value_quality_growth_metrics as mod

    cursor = _RecordingCursor()

    class _FakeDatabaseContext:
        def __enter__(self):
            return cursor

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    loader = _make_loader()
    with patch.object(loader, "_get_analyst_forward_eps", return_value=None):
        return loader._build_value_metrics("NETCASH", _FakeSecValRow(sec_val_fields))


class TestEvRevenueEvEbitdaNegativeEnterpriseValueReason:
    def test_net_cash_exceeding_market_cap_gets_negative_ev_reason(self, monkeypatch):
        result = _run(
            monkeypatch,
            pe_ratio=15.0,
            pb_ratio=2.0,
            ps_ratio=3.0,
            ev_revenue=None,
            ev_ebitda=None,
            ebitda=5_000_000.0,
            enterprise_value=None,
            market_cap=20_000_000.0,
            total_debt=1_000_000.0,
            total_cash=30_000_000.0,  # cash alone exceeds market_cap + debt -> EV <= 0
            fcf_yield=6.0,
        )

        assert result["ev_revenue_unavailable_reason"] == "negative_enterprise_value"
        assert result["ev_ebitda_unavailable_reason"] == "negative_enterprise_value"

    def test_positive_ev_keeps_generic_reason_when_not_extracted(self, monkeypatch):
        result = _run(
            monkeypatch,
            pe_ratio=15.0,
            pb_ratio=2.0,
            ps_ratio=3.0,
            ev_revenue=None,
            ev_ebitda=None,
            ebitda=5_000_000.0,
            enterprise_value=None,
            market_cap=20_000_000.0,
            total_debt=1_000_000.0,
            total_cash=5_000_000.0,  # market_cap + debt - cash = 16M, positive
            fcf_yield=6.0,
        )

        assert result["ev_revenue_unavailable_reason"] == "missing_sec_data"
        assert result["ev_ebitda_unavailable_reason"] == "missing_sec_data"

    def test_missing_market_cap_does_not_crash_and_keeps_generic_reason(self, monkeypatch):
        result = _run(
            monkeypatch,
            pe_ratio=15.0,
            pb_ratio=2.0,
            ps_ratio=3.0,
            ev_revenue=None,
            ev_ebitda=None,
            ebitda=5_000_000.0,
            enterprise_value=None,
            market_cap=None,
            fcf_yield=6.0,
        )

        assert result["ev_revenue_unavailable_reason"] == "missing_sec_data"
        assert result["ev_ebitda_unavailable_reason"] == "missing_sec_data"
