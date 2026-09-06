"""Regression test (2026-09-06, goal: "SEC/XBRL missing data to zero" sweep, comprehensive
RIC-gap scan): ev_ebitda's reason chain reused the "total_debt_not_itemized" branch (same gate
as quality_metrics.total_debt) without ever checking registered-investment-company (RIC)
status first, unlike quality_metrics.total_debt/roic_pct/roce_pct/debt_to_equity (all already
recategorized). A RIC has no debt concept to tag at all (files a "Statement of Changes in Net
Assets"), same structural fact - live-confirmed CEV (real ebitda>0, no debt concept) was
falling to the generic "total_debt_not_itemized" ("Missing SEC/XBRL data") instead of
"registered_investment_company_no_xbrl" ("Legitimate / not applicable").
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class _FakeSecValRow:
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


def _run(monkeypatch, symbol, ric_symbols=frozenset(), **sec_val_fields):
    import loaders.load_value_quality_growth_metrics as mod

    cursor = _RecordingCursor()

    class _FakeDatabaseContext:
        def __enter__(self):
            return cursor

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    loader = _make_loader()
    monkeypatch.setattr(loader, "_get_registered_investment_company_symbols", lambda: ric_symbols, raising=False)
    monkeypatch.setattr(loader, "_get_no_recent_debt_components_symbols", lambda: frozenset(), raising=False)
    with patch.object(loader, "_get_analyst_forward_eps", return_value=None):
        return loader._build_value_metrics(symbol, _FakeSecValRow(sec_val_fields))


class TestEvEbitdaRicRecategorize:
    def test_ric_with_real_ebitda_reports_registered_investment_company_reason(self, monkeypatch):
        result = _run(
            monkeypatch,
            "CEV",
            ric_symbols=frozenset({"CEV"}),
            pe_ratio=15.0,
            pb_ratio=2.0,
            ps_ratio=3.0,
            ev_revenue=None,
            ev_ebitda=None,
            ebitda=5_000_000.0,
            enterprise_value=None,
            market_cap=20_000_000.0,
            total_debt=None,
            total_cash=None,
            fcf_yield=6.0,
        )

        assert result["ev_ebitda_unavailable_reason"] == "registered_investment_company_no_xbrl"

    def test_non_ric_keeps_total_debt_not_itemized(self, monkeypatch):
        import loaders.load_value_quality_growth_metrics as mod

        cursor = _RecordingCursor()

        class _FakeDatabaseContext:
            def __enter__(self):
                return cursor

            def __exit__(self, *exc):
                return False

        monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
        loader = _make_loader()
        monkeypatch.setattr(loader, "_get_registered_investment_company_symbols", lambda: frozenset(), raising=False)
        monkeypatch.setattr(
            loader, "_get_no_recent_debt_components_symbols", lambda: frozenset({"NORMALCO"}), raising=False
        )
        with patch.object(loader, "_get_analyst_forward_eps", return_value=None):
            result = loader._build_value_metrics(
                "NORMALCO",
                _FakeSecValRow(
                    {
                        "pe_ratio": 15.0,
                        "pb_ratio": 2.0,
                        "ps_ratio": 3.0,
                        "ev_revenue": None,
                        "ev_ebitda": None,
                        "ebitda": 5_000_000.0,
                        "enterprise_value": None,
                        "market_cap": 20_000_000.0,
                        "total_debt": None,
                        "total_cash": None,
                        "fcf_yield": 6.0,
                    }
                ),
            )

        assert result["ev_ebitda_unavailable_reason"] == "total_debt_not_itemized"
