"""Regression test (2026-08-19, financial-calc accuracy audit goal): roe, roa,
debt_to_equity, debt_to_assets, current_ratio, and quick_ratio were the only members of
the loaders/load_value_quality_growth_metrics.py ratio family missing the |ratio| > 1000
near-zero-denominator garbage-value bound that gross_margin, ebitda_margin, roic_pct,
operating_margin, net_margin, and interest_coverage already had (see
test_quality_metrics_implausible_ratio_reason.py for that established pattern).

Live DB audit found real, uncapped garbage from this gap: KWM roe=-6,832,939%,
SNDA roe=643,445% (83 symbols system-wide with |roe| > 1000%); EROC
debt_to_equity=8,508, CCII=2,901, WHLR=3,747 (60 symbols with |debt_to_equity| > 100);
BCAR current_ratio=1056.74. These feed quality_score and cross-symbol comparison
directly as extreme, unsuppressed outliers - the exact same failure mode the sibling
metrics were already fixed for.
"""

import pytest

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
    stockholders_equity=None,
    total_liabilities=200_000_000.0,
    total_assets=700_000_000.0,
    net_income=50_000_000.0,
    revenue=None,
    operating_income=None,
    current_assets=150_000_000.0,
    current_liabilities=100_000_000.0,
    inventory=None,
    cost_of_revenue=None,
    gross_profit=None,
    long_term_debt=None,
    cash_and_equivalents=None,
    income_tax_expense=None,
    pretax_income=None,
    interest_expense=None,
):
    # Same 34-column shape as test_quality_metrics_implausible_ratio_reason.py's fixture,
    # with total_liabilities/total_assets/net_income/current_assets/current_liabilities
    # parameterized (fixed there) so debt/liquidity ratios can be pushed past the bound.
    return (
        stockholders_equity,  # 0
        total_liabilities,  # 1
        total_assets,  # 2
        net_income,  # 3
        revenue,  # 4
        operating_income,  # 5
        current_assets,  # 6
        current_liabilities,  # 7
        2025,  # 8 fiscal_year
        inventory,  # 9
        interest_expense,  # 10
        None,  # 11 shares_outstanding
        cost_of_revenue,  # 12
        None,  # 13 operating_cash_flow
        None,  # 14 free_cash_flow
        None,  # 15 dividends_paid
        None,  # 16 earnings_per_share
        None,  # 17 prior_year_eps
        None,  # 18 prior_year_revenue
        gross_profit,  # 19
        long_term_debt,  # 20
        cash_and_equivalents,  # 21
        income_tax_expense,  # 22
        pretax_income,  # 23
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


class TestRoeRoaDebtRatioImplausibleBound:
    def test_roe_bound_reports_implausible_ratio(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        # net_income=50M / stockholders_equity=1M -> 5000%, past the >1000% bound.
        row = _quality_row(stockholders_equity=1_000_000.0)

        metrics = loader._compute_quality_metrics("KWM", row, ev_metrics=None)

        assert metrics["roe"] is None
        assert metrics["roe_unavailable_reason"] == "implausible_ratio"

    def test_roa_bound_reports_implausible_ratio(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        # net_income=50M / total_assets=1M -> 5000%, past the >1000% bound.
        row = _quality_row(stockholders_equity=100_000_000.0, total_assets=1_000_000.0)

        metrics = loader._compute_quality_metrics("SNDA", row, ev_metrics=None)

        assert metrics["roa"] is None
        assert metrics["roa_unavailable_reason"] == "implausible_ratio"

    def test_debt_to_equity_bound_reports_implausible_ratio(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        # total_liabilities=200M / stockholders_equity=10,000 -> 20,000x, past the bound.
        row = _quality_row(stockholders_equity=10_000.0)

        metrics = loader._compute_quality_metrics("EROC", row, ev_metrics=None)

        assert metrics["debt_to_equity"] is None
        assert metrics["debt_to_equity_unavailable_reason"] == "implausible_ratio"

    def test_debt_to_assets_bound_reports_implausible_ratio(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        # total_liabilities=200M / total_assets=10,000 -> 20,000x, past the bound.
        row = _quality_row(stockholders_equity=100_000_000.0, total_assets=10_000.0)

        metrics = loader._compute_quality_metrics("BADASSETS", row, ev_metrics=None)

        assert metrics["debt_to_assets"] is None
        assert metrics["debt_to_assets_unavailable_reason"] == "implausible_ratio"

    def test_current_ratio_bound_reports_implausible_ratio(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        # current_assets=150M / current_liabilities=10,000 -> 15,000x, past the bound.
        row = _quality_row(stockholders_equity=100_000_000.0, current_liabilities=10_000.0)

        metrics = loader._compute_quality_metrics("BCAR", row, ev_metrics=None)

        assert metrics["current_ratio"] is None
        assert metrics["current_ratio_unavailable_reason"] == "implausible_ratio"

    def test_quick_ratio_bound_reports_implausible_ratio(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(stockholders_equity=100_000_000.0, current_liabilities=10_000.0)

        metrics = loader._compute_quality_metrics("BCAR2", row, ev_metrics=None)

        assert metrics["quick_ratio"] is None
        assert metrics["quick_ratio_unavailable_reason"] == "implausible_ratio"

    def test_genuine_values_within_bound_still_compute(self, monkeypatch):
        # Control: ordinary, plausible inputs must keep computing real values, not be
        # accidentally suppressed by the new bound.
        loader = _make_loader(monkeypatch)
        row = _quality_row(stockholders_equity=100_000_000.0)

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["roe"] == pytest.approx(50.0)
        assert metrics["roe_unavailable_reason"] is None
        assert metrics["roa"] == pytest.approx((50_000_000.0 / 700_000_000.0) * 100)
        assert metrics["debt_to_equity"] == pytest.approx(2.0)
        assert metrics["debt_to_equity_unavailable_reason"] is None
        assert metrics["current_ratio"] == pytest.approx(1.5)
        assert metrics["current_ratio_unavailable_reason"] is None
