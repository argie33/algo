"""Direct unit coverage for earnings_variability (loaders/helpers/quality_variability.py) - the
new, untracked MSCI Earnings Variability module added in the same 2026-09-16 factor-purity
/goal session as growth_trend.py's ols_growth_trend, but (unlike that module) shipped without
its own dedicated test file - see test_growth_trend_msci_ols_formula_20260916.py for the sibling
this mirrors. MSCI states no worked numerical example for this specific variable (unlike the
Growth trend formula), so this file proves the formula/edge-case behavior directly against the
module's own stated contract rather than reproducing a published worked example.
"""

import statistics

from loaders.helpers.quality_variability import (
    MAX_YEARS_FOR_VARIABILITY,
    MIN_YEARS_FOR_VARIABILITY,
    earnings_variability,
)


class TestFormula:
    def test_matches_pstdev_of_yoy_growth_rates(self):
        # EPS 1.00 -> 1.20 -> 1.10 -> 1.50: YoY growth rates 0.20, -0.08333.., 0.363636...
        values = [(2020, 1.00), (2021, 1.20), (2022, 1.10), (2023, 1.50)]
        growth_rates = [(1.20 - 1.00) / 1.00, (1.10 - 1.20) / 1.20, (1.50 - 1.10) / 1.10]
        expected = statistics.pstdev(growth_rates) * 100.0
        result = earnings_variability(values)
        assert result is not None
        assert round(result, 6) == round(expected, 6)

    def test_order_independent(self):
        values = [(2020, 1.00), (2021, 1.20), (2022, 1.10), (2023, 1.50)]
        shuffled = [values[2], values[0], values[3], values[1]]
        assert round(earnings_variability(shuffled), 6) == round(earnings_variability(values), 6)

    def test_flat_series_returns_zero_not_none(self):
        result = earnings_variability([(2020, 2.0), (2021, 2.0), (2022, 2.0)])
        assert result == 0.0

    def test_negative_to_positive_swing_uses_absolute_value_denominator(self):
        # prior=-1.0, curr=1.0 -> growth = (1.0 - (-1.0)) / abs(-1.0) = 2.0, a well-defined,
        # non-exploding rate - the same sign-safe convention this codebase uses elsewhere.
        values = [(2020, -1.0), (2021, 1.0), (2022, 1.0)]
        expected_rates = [2.0, 0.0]
        result = earnings_variability(values)
        assert result is not None
        assert round(result, 6) == round(statistics.pstdev(expected_rates) * 100.0, 6)


class TestMinimumYearsFloor:
    def test_below_minimum_years_returns_none(self):
        values = [(2020, 1.0), (2021, 1.2)]
        assert len(values) < MIN_YEARS_FOR_VARIABILITY
        assert earnings_variability(values) is None

    def test_at_minimum_years_returns_real_value(self):
        values = [(2020, 1.0), (2021, 1.2), (2022, 1.1)]
        assert len(values) == MIN_YEARS_FOR_VARIABILITY
        result = earnings_variability(values)
        assert result is not None
        assert isinstance(result, float)

    def test_uses_only_most_recent_five_years(self):
        base = [(2019, 1.0), (2020, 1.2), (2021, 1.1), (2022, 1.5), (2023, 1.3)]
        assert len(base) == MAX_YEARS_FOR_VARIABILITY
        with_extra_old_year = [(2010, 999.0), *base]
        assert round(earnings_variability(with_extra_old_year), 6) == round(earnings_variability(base), 6)


class TestDegenerateCases:
    def test_every_prior_year_zero_base_returns_none(self):
        # Every YoY pair has a zero prior-year base -> zero real growth-rate observations.
        assert earnings_variability([(2020, 0.0), (2021, 0.0), (2022, 0.0)]) is None

    def test_only_one_real_growth_observation_returns_none(self):
        # 3 years but one prior-year base is zero -> only 1 real growth rate, below the
        # "at least 2 observations" floor a population stdev needs to be non-trivial.
        assert earnings_variability([(2020, 0.0), (2021, 1.0), (2022, 1.1)]) is None
