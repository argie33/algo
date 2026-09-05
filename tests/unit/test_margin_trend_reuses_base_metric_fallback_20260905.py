"""Regression test (2026-09-05, "SEC/XBRL missing data to zero" goal session):
operating_margin_trend/net_margin_trend/gross_margin_trend/roe_trend each independently
recompute the current year's margin/ROE from raw fields instead of reusing the base metric's
own already-computed value - so when the base metric (operating_margin etc.) rescues an
implausible current-year ratio via its cross-year fallback (this session's earlier fixes), the
trend field didn't benefit and still went straight to implausible_ratio.

Fix: each trend field now prefers `metrics.get("operating_margin")` (etc.) - already resolved,
possibly via the fallback - falling back to the raw computation only when the base metric
itself has no value (e.g. net_income == 0, which never enters the implausible branch at all).
"""

import pytest

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


class _FakeCursor:
    def __init__(self, fallback_rows):
        self._fallback_rows = fallback_rows
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        if "ais.net_income" in self._last_query and "ais.gross_profit" in self._last_query:
            return self._fallback_rows
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, fallback_rows):
        self._fallback_rows = fallback_rows

    def __enter__(self):
        return _FakeCursor(self._fallback_rows)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, fallback_rows):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(fallback_rows))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def _quality_row(revenue, operating_income, prior_year_revenue, prior_year_operating_income):
    # Same 33-column shape as test_quality_metrics_implausible_ratio_reason.py's fixture.
    return (
        100_000_000.0,  # 0 stockholders_equity
        200_000_000.0,  # 1 total_liabilities
        700_000_000.0,  # 2 total_assets
        50_000_000.0,  # 3 net_income
        revenue,  # 4
        operating_income,  # 5
        150_000_000.0,  # 6 current_assets
        100_000_000.0,  # 7 current_liabilities
        2025,  # 8 fiscal_year
        None,  # 9 inventory
        None,  # 10 interest_expense
        None,  # 11 shares_outstanding
        None,  # 12 cost_of_revenue
        None,  # 13 operating_cash_flow
        None,  # 14 free_cash_flow
        None,  # 15 dividends_paid
        None,  # 16 earnings_per_share
        None,  # 17 prior_year_eps
        prior_year_revenue,  # 18
        None,  # 19 gross_profit
        None,  # 20 long_term_debt
        None,  # 21 cash_and_equivalents
        None,  # 22 income_tax_expense
        None,  # 23 pretax_income
        50_000_000.0,  # 24 prior_year_net_income
        prior_year_operating_income,  # 25
        None,  # 26 prior_year_operating_cash_flow
        None,  # 27 prior_year_free_cash_flow
        None,  # 28 prior_year_cost_of_revenue
        None,  # 29 prior_year_total_assets
        None,  # 30 prior_year_stockholders_equity
        None,  # 31 prior_year_pretax_income
        None,  # 32 prior_year_interest_expense
        None,  # 33 prior_year_gross_profit
    )


def test_operating_margin_trend_uses_rescued_current_year_operating_margin(monkeypatch):
    # Current year: revenue near-zero -> raw operating_margin implausible, rescued by the
    # cross-year fallback to 10% (fallback row: operating_income=100M, revenue=1000M).
    # Prior year: operating_income=100M / revenue=900M = 11.11% - plausible on its own.
    fallback_row = (8_000_000.0, 100_000_000.0, 50_000_000.0, 1_000_000_000.0, 100_000_000.0, 1_000_000.0, 40_000_000.0)
    loader = _make_loader(monkeypatch, [fallback_row])
    row = _quality_row(
        revenue=1_000.0,
        operating_income=50_000_000.0,
        prior_year_revenue=900_000_000.0,
        prior_year_operating_income=100_000_000.0,
    )

    metrics = loader._compute_quality_metrics("ZZZZ", row, ev_metrics=None)

    assert metrics["operating_margin"] == pytest.approx(10.0)
    assert "operating_margin_trend" in metrics
    assert metrics.get("operating_margin_trend_unavailable_reason") is None
