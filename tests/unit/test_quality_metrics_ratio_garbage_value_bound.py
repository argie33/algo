"""Regression test: gross_margin, ebitda_margin, and roic_pct must be bounded against the
same near-zero-denominator garbage-value class already fixed for interest_coverage (see
test_interest_coverage_ebit_fallback.py / interest_coverage_roic_ebit_approximation_fix_20260809
memory) - that fix was scoped only to interest_coverage's own code block and missed the
identical division pattern in these three adjacent metrics.

Live DB audit (2026-08-09) found real, already-written garbage values from exactly this gap:
99 symbols with |gross_margin| > 1000% (worst: CRML at 23,148,148%, from a quarter reporting
revenue=$540 against gross_profit=$125,000,000 - almost certainly a mis-scaled/mis-tagged SEC
fact, not real data), 274 symbols with |ebitda_margin| > 1000%, and MCK at roic_pct=1347.77%
(from invested_capital being real but implausibly close to zero, same failure mode as the
already-fixed interest_coverage near-zero-interest-expense case). All three are now bounded at
|ratio| <= 1000, mirroring interest_coverage's existing bound exactly.
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
    stockholders_equity=None,
    revenue=None,
    operating_income=None,
    cost_of_revenue=None,
    gross_profit=None,
    long_term_debt=None,
    cash_and_equivalents=None,
    income_tax_expense=None,
    pretax_income=None,
):
    # Same 31-column shape as test_interest_coverage_ebit_fallback.py's fixture.
    return (
        stockholders_equity,  # 0
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
    )


class TestGrossMarginGarbageValueBound:
    def test_implausible_ratio_from_mismatched_revenue_marked_unavailable(self, monkeypatch):
        # CRML-shaped: gross_profit real-scale, revenue implausibly tiny relative to it.
        loader = _make_loader(monkeypatch)
        row = _quality_row(gross_profit=125_000_000.0, revenue=540.0)

        metrics = loader._compute_quality_metrics("CRML", row, ev_metrics=None)

        assert metrics["gross_margin"] is None

    def test_normal_ratio_still_computes(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(gross_profit=82_331_000.0, revenue=119_413_000.0)

        metrics = loader._compute_quality_metrics("AUDC", row, ev_metrics=None)

        assert metrics["gross_margin"] == (82_331_000.0 / 119_413_000.0) * 100


class TestEbitdaMarginGarbageValueBound:
    def test_implausible_ratio_marked_unavailable(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(revenue=2_454_000.0)
        # ev_metrics = (total_debt, total_cash, ebitda)
        ev_metrics = (None, None, 155_771_000.0)

        metrics = loader._compute_quality_metrics("CLBT", row, ev_metrics=ev_metrics)

        assert metrics["ebitda_margin"] is None

    def test_normal_ratio_still_computes(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(revenue=400_000_000.0)
        ev_metrics = (None, None, 100_000_000.0)

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=ev_metrics)

        assert metrics["ebitda_margin"] == 25.0


class TestRoicPctGarbageValueBound:
    def test_near_zero_invested_capital_marked_unavailable(self, monkeypatch):
        # MCK-shaped: real but near-zero invested_capital (negative equity mostly offset by
        # debt, minimal cash) explodes the ratio despite a perfectly ordinary NOPAT.
        loader = _make_loader(monkeypatch)
        row = _quality_row(
            stockholders_equity=-999_000_000.0,
            long_term_debt=1_000_000_000.0,
            cash_and_equivalents=500_000.0,
            operating_income=10_000_000.0,
            income_tax_expense=2_000_000.0,
            pretax_income=10_000_000.0,
        )

        metrics = loader._compute_quality_metrics("MCK", row, ev_metrics=None)

        assert metrics["roic_pct"] is None

    def test_normal_ratio_still_computes(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(
            stockholders_equity=500_000_000.0,
            long_term_debt=200_000_000.0,
            cash_and_equivalents=50_000_000.0,
            operating_income=100_000_000.0,
            income_tax_expense=20_000_000.0,
            pretax_income=100_000_000.0,
        )

        metrics = loader._compute_quality_metrics("NORMALCO2", row, ev_metrics=None)

        invested_capital = 500_000_000.0 + 200_000_000.0 - 50_000_000.0
        nopat = 100_000_000.0 * (1 - 0.2)
        assert metrics["roic_pct"] == (nopat / invested_capital) * 100
