"""Regression test for load_enhanced_quality_growth_metrics.py's *_margin_trend/roe_trend fields.

Covers the margin-trend block in fetch_incremental(): this loader recomputes gross/operating/
net margin independently from raw annual_income_statement rows (same revenue-denominator
division pattern already bounded in load_value_quality_growth_metrics.py by commits 12063b32a/
5ceda9952 - gross_margin/ebitda_margin/roic_pct/operating_margin/net_margin all bounded at
|ratio| <= 1000), but never inherited that bound. Live-observed on the dashboard: Op Margin
Trend +3545.1K pp and Net Margin Trend +787.78pp, alongside a now-correctly-bounded current-year
operating_margin - a garbage current- or prior-year margin (near-zero revenue) was flowing
straight into *_margin_trend/roe_trend with no bound at all.
"""

from loaders.load_enhanced_quality_growth_metrics import EnhancedQualityGrowthMetricsLoader


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, query, params=None):
        pass

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeDatabaseContext:
    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return _FakeCursor(self._rows)

    def __exit__(self, *exc):
        return False


def _loader(monkeypatch, income_rows, margin_rows):
    import loaders.load_enhanced_quality_growth_metrics as mod

    contexts = iter([_FakeDatabaseContext(income_rows), _FakeDatabaseContext(margin_rows)])
    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: next(contexts))
    loader = EnhancedQualityGrowthMetricsLoader.__new__(EnhancedQualityGrowthMetricsLoader)
    # Out of scope for this test - covered separately by
    # test_load_enhanced_quality_growth_metrics_revision_fields.py and would otherwise hit
    # real DB/yfinance calls unmocked here.
    monkeypatch.setattr(loader, "_compute_quarterly_metrics", lambda *a, **k: None)
    monkeypatch.setattr(loader, "_compute_earnings_surprise_metrics", lambda *a, **k: None)
    monkeypatch.setattr(loader, "_compute_estimate_revision_metrics", lambda *a, **k: None)
    return loader


# income_rows columns: fiscal_year, revenue, operating_income, net_income, total_assets,
# stockholders_equity, current_liabilities, operating_cash_flow, financing_cash_flow
def _income_row(fy, revenue, operating_income, net_income, equity=500_000_000.0):
    return (fy, revenue, operating_income, net_income, 1_000_000_000.0, equity, 100_000_000.0, None, None)


# margin_rows columns: fiscal_year, cost_of_revenue, gross_profit
def _margin_row(fy, cost_of_revenue, gross_profit):
    return (fy, cost_of_revenue, gross_profit)


class TestMarginTrendBound:
    def test_near_zero_current_revenue_does_not_blow_up_operating_margin_trend(self, monkeypatch):
        # Mirrors the live KARO-shaped bug: near-zero current-year revenue against a real
        # operating_income explodes the raw margin into thousands of percent. gross_profit/
        # net_income are scaled down to match the tiny revenue (still plausible margins) so
        # this isolates operating_margin_trend as the only field that should be dropped.
        income_rows = [
            _income_row(2025, revenue=1_000.0, operating_income=50_000_000.0, net_income=500.0),
            _income_row(2024, revenue=1_000_000_000.0, operating_income=100_000_000.0, net_income=50_000_000.0),
        ]
        margin_rows = [
            _margin_row(2025, cost_of_revenue=500.0, gross_profit=500.0),
            _margin_row(2024, cost_of_revenue=600_000_000.0, gross_profit=400_000_000.0),
        ]
        loader = _loader(monkeypatch, income_rows, margin_rows)

        result = loader.fetch_incremental("ZZZZ", None)
        metrics = result[0]

        assert "operating_margin_trend" not in metrics

    def test_two_plausible_years_produce_a_bounded_trend(self, monkeypatch):
        income_rows = [
            _income_row(2025, revenue=1_000_000_000.0, operating_income=150_000_000.0, net_income=100_000_000.0),
            _income_row(2024, revenue=900_000_000.0, operating_income=100_000_000.0, net_income=80_000_000.0),
        ]
        margin_rows = [
            _margin_row(2025, cost_of_revenue=600_000_000.0, gross_profit=400_000_000.0),
            _margin_row(2024, cost_of_revenue=550_000_000.0, gross_profit=350_000_000.0),
        ]
        loader = _loader(monkeypatch, income_rows, margin_rows)

        result = loader.fetch_incremental("AAPL", None)
        metrics = result[0]

        assert metrics["operating_margin_trend"] is not None
        assert abs(metrics["operating_margin_trend"]) <= 1000
        assert metrics["net_margin_trend"] is not None
        assert metrics["gross_margin_trend"] is not None

    def test_near_zero_prior_equity_does_not_blow_up_roe_trend(self, monkeypatch):
        income_rows = [
            _income_row(2025, revenue=1_000_000_000.0, operating_income=150_000_000.0, net_income=100_000_000.0, equity=500_000_000.0),
            _income_row(2024, revenue=900_000_000.0, operating_income=100_000_000.0, net_income=80_000_000.0, equity=100.0),
        ]
        margin_rows = [
            _margin_row(2025, cost_of_revenue=600_000_000.0, gross_profit=400_000_000.0),
            _margin_row(2024, cost_of_revenue=550_000_000.0, gross_profit=350_000_000.0),
        ]
        loader = _loader(monkeypatch, income_rows, margin_rows)

        result = loader.fetch_incremental("YYYY", None)
        metrics = result[0]

        assert "roe_trend" not in metrics
