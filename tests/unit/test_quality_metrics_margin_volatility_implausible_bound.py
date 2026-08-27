"""Regression test (2026-08-26, live-caught): `_compute_margin_volatility` computed each
fiscal year's raw net_margin inline with NO implausible-value bound, unlike every sibling
margin ratio in this file (net_margin/gross_margin/operating_margin/fcf_margin all guard
|ratio|>1000 - see test_quality_metrics_implausible_ratio_reason.py). A near-zero-revenue year
(SEC tagging garbage, not a real business characteristic) produced a margin in the billions of
percent; squaring+sqrt-ing that in the variance calc overflowed quality_metrics.margin_volatility's
NUMERIC(10,2) column, crashing the ENTIRE row's INSERT for that symbol - live-caught: TKLF,
`psycopg2.errors.NumericValueOutOfRange: numeric field overflow` during a full-universe
value_quality_growth refresh, blocking its whole quality_metrics write (not just this one field).
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def _income_row(fiscal_year, revenue, net_income):
    # (fiscal_year, revenue, operating_income, net_income, eps, shares_diluted, shares_basic) -
    # matches fetch_incremental's SELECT order; only revenue/net_income matter here.
    return (fiscal_year, revenue, None, net_income, None, None, None)


class TestMarginVolatilityImplausibleBound:
    def test_near_zero_revenue_year_excluded_not_crashed(self):
        loader = _make_loader()
        # TKLF-like case: one year with near-zero revenue produces an astronomical margin
        # (10_000_000 / 1.0 * 100 = 1_000_000_000%) - only 2 real usable years remain, below
        # the 3-year minimum, so this must return None/implausible_ratio, not a garbage stdev.
        rows = [
            _income_row(2025, 50_000_000.0, 5_000_000.0),
            _income_row(2024, 1.0, 10_000_000.0),
            _income_row(2023, 45_000_000.0, 4_000_000.0),
        ]

        value, reason = loader._compute_margin_volatility(rows)

        assert value is None
        assert reason == "implausible_ratio"

    def test_three_normal_years_computes_real_stdev(self):
        loader = _make_loader()
        rows = [
            _income_row(2025, 100_000_000.0, 12_000_000.0),
            _income_row(2024, 95_000_000.0, 10_000_000.0),
            _income_row(2023, 90_000_000.0, 9_000_000.0),
        ]

        value, reason = loader._compute_margin_volatility(rows)

        assert value is not None
        assert 0.0 <= value < 100.0
        assert reason is None

    def test_insufficient_years_still_reports_insufficient_history(self):
        loader = _make_loader()
        rows = [_income_row(2025, 100_000_000.0, 12_000_000.0)]

        value, reason = loader._compute_margin_volatility(rows)

        assert value is None
        assert reason == "insufficient_history"
