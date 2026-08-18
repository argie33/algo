"""Regression test: earnings_growth_yoy/revenue_growth_yoy were missing the
MAX_TREND_PERCENTAGE_POINTS overflow guard every sibling *_growth_yoy field in this loader
already has (net_income_growth_yoy, operating_income_growth_yoy, fcf_growth_yoy,
ocf_growth_yoy, asset_growth_yoy - see that guard's ANET FY2024 docstring example).

Live-confirmed 2026-08-16: GLPI's quality_metrics INSERT failed with NumericValueOutOfRange - a
real but near-zero prior-year EPS/revenue base produces a percentage that overflows
earnings_growth_yoy/revenue_growth_yoy's NUMERIC(10,2) column (max magnitude 99,999,999.99) and
crashed the INSERT for the whole row, losing every other metric in it too - the exact same
crash-and-lose-everything failure mode already fixed for the sibling growth_yoy fields.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


class _FakeCursor:
    def execute(self, query, params=None):
        pass

    def fetchall(self):
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __enter__(self):
        return _FakeCursor()

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def _quality_row(earnings_per_share=None, prior_year_eps=None, revenue=None, prior_year_revenue=None):
    # Same 33-column shape as test_quality_metrics_dollar_and_quarterly_garbage_value_bound.py.
    return (
        500_000_000.0,  # 0 stockholders_equity
        200_000_000.0,  # 1 total_liabilities
        700_000_000.0,  # 2 total_assets
        50_000_000.0,  # 3 net_income
        revenue if revenue is not None else 200_000_000.0,  # 4 revenue
        30_000_000.0,  # 5 operating_income
        150_000_000.0,  # 6 current_assets
        100_000_000.0,  # 7 current_liabilities
        2025,  # 8 fiscal_year
        None,  # 9 inventory
        None,  # 10 interest_expense
        None,  # 11 shares_outstanding
        120_000_000.0,  # 12 cost_of_revenue
        None,  # 13 operating_cash_flow
        None,  # 14 free_cash_flow
        None,  # 15 dividends_paid
        earnings_per_share,  # 16 earnings_per_share
        prior_year_eps,  # 17 prior_year_eps
        prior_year_revenue,  # 18 prior_year_revenue
        80_000_000.0,  # 19 gross_profit
        None,  # 20 long_term_debt
        None,  # 21 cash_and_equivalents
        None,  # 22 income_tax_expense
        None,  # 23 pretax_income
        None,  # 24 prior_year_net_income
        None,  # 25 prior_year_operating_income
        None,  # 26 prior_year_operating_cash_flow
        None,  # 27 prior_year_free_cash_flow
        None,  # 28 prior_year_cost_of_revenue
        None,  # 29 prior_year_total_assets
        None,  # 30 prior_year_stockholders_equity
        None,  # 31 prior_year_pretax_income
        None,  # 32 prior_year_interest_expense
        None,  # 33 prior_year_gross_profit
    )


class TestEarningsRevenueGrowthYoyOverflowBound:
    def test_near_zero_prior_year_eps_marked_unavailable_not_crashed(self, monkeypatch):
        # GLPI-shaped: a real but near-zero prior-year EPS makes the YoY growth ratio
        # mathematically enormous - must be bounded, not left to overflow the DB column.
        loader = _make_loader(monkeypatch)
        row = _quality_row(earnings_per_share=5.00, prior_year_eps=0.0001)

        metrics = loader._compute_quality_metrics("GLPI", row, ev_metrics=None)

        assert metrics.get("earnings_growth_yoy") is None

    def test_near_zero_prior_year_revenue_marked_unavailable_not_crashed(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(revenue=200_000_000.0, prior_year_revenue=0.01)

        metrics = loader._compute_quality_metrics("GLPI", row, ev_metrics=None)

        assert metrics.get("revenue_growth_yoy") is None

    def test_normal_earnings_and_revenue_growth_still_compute(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(
            earnings_per_share=5.50, prior_year_eps=5.00, revenue=210_000_000.0, prior_year_revenue=200_000_000.0
        )

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics.get("earnings_growth_yoy") == 10.0
        assert metrics.get("revenue_growth_yoy") == 5.0
