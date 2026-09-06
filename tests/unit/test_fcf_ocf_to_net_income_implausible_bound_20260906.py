"""Regression test (goal session 2026-09-06, "implausible values" sweep continuation): fcf_to_
net_income and ocf_to_net_income were the only two members of vqg_quality.py's ratio family
still missing the |ratio| > 1000 near-zero-denominator garbage-value bound that debt_to_assets/
current_ratio/quick_ratio/debt_to_equity/roe/roa/roic_pct/roce_pct/gross_margin/ebitda_margin/
interest_coverage all already have (see test_quality_metrics_roe_debt_ratio_implausible_bound.py
for that established pattern) - a near-zero net_income denominator explodes both ratios exactly
the same way a near-zero equity/assets base explodes the others, but nothing capped it, and
their _unavailable_reason cascades had no "implausible_ratio" branch either (every sibling ratio's
does), so a rejected value would have silently fallen to the generic "missing_sec_data" reason
even if a bound had existed. Fixed by adding both the bound and the reason-cascade branch,
mirroring debt_to_assets_unavailable_reason's exact pattern.
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


def _quality_row(
    net_income=50_000_000.0,
    operating_cash_flow=None,
    free_cash_flow=None,
    stockholders_equity=100_000_000.0,
    total_liabilities=200_000_000.0,
    total_assets=700_000_000.0,
    current_assets=150_000_000.0,
    current_liabilities=100_000_000.0,
):
    # Same 34-column shape as test_quality_metrics_roe_debt_ratio_implausible_bound.py's
    # fixture, with operating_cash_flow/free_cash_flow (indices 13/14) now parameterized.
    return (
        stockholders_equity,  # 0
        total_liabilities,  # 1
        total_assets,  # 2
        net_income,  # 3
        None,  # 4 revenue
        None,  # 5 operating_income
        current_assets,  # 6
        current_liabilities,  # 7
        2025,  # 8 fiscal_year
        None,  # 9 inventory
        None,  # 10 interest_expense
        None,  # 11 shares_outstanding
        None,  # 12 cost_of_revenue
        operating_cash_flow,  # 13
        free_cash_flow,  # 14
        None,  # 15 dividends_paid
        None,  # 16 earnings_per_share
        None,  # 17 prior_year_eps
        None,  # 18 prior_year_revenue
        None,  # 19 gross_profit
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


class TestFcfOcfToNetIncomeImplausibleBound:
    def test_fcf_to_net_income_bound_reports_implausible_ratio(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        # free_cash_flow=50M / net_income=10,000 -> 5000x, past the >1000 bound.
        row = _quality_row(net_income=10_000.0, free_cash_flow=50_000_000.0)

        metrics = loader._compute_quality_metrics("FCFBLOWUP", row, ev_metrics=None)

        assert metrics["fcf_to_net_income"] is None
        assert metrics["fcf_to_net_income_unavailable_reason"] == "implausible_ratio"

    def test_ocf_to_net_income_bound_reports_implausible_ratio(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        # operating_cash_flow=50M / net_income=10,000 -> 5000x, past the >1000 bound.
        row = _quality_row(net_income=10_000.0, operating_cash_flow=50_000_000.0)

        metrics = loader._compute_quality_metrics("OCFBLOWUP", row, ev_metrics=None)

        assert metrics["ocf_to_net_income"] is None
        assert metrics["ocf_to_net_income_unavailable_reason"] == "implausible_ratio"

    def test_genuine_values_within_bound_still_compute(self, monkeypatch):
        # Control: ordinary, plausible inputs must keep computing real values, not be
        # accidentally suppressed by the new bound.
        loader = _make_loader(monkeypatch)
        row = _quality_row(net_income=50_000_000.0, free_cash_flow=40_000_000.0, operating_cash_flow=60_000_000.0)

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["fcf_to_net_income"] == 0.8
        assert metrics["fcf_to_net_income_unavailable_reason"] is None
        assert metrics["ocf_to_net_income"] == 1.2
        assert metrics["ocf_to_net_income_unavailable_reason"] is None
