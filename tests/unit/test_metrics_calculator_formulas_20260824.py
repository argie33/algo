"""Direct unit tests for utils/metrics_calculator.py's MetricsCalculator - the module's own
docstring calls it "the ONLY place where these metrics should be calculated" (used by
algo/reporting/performance.py, exposed via the API/dashboard, persisted to
algo_performance_daily), yet it had ZERO direct unit tests anywhere in the suite before this
file - every existing reference only exercised it indirectly through performance.py mocks.
Found during the 2026-08-24 finance-formula /goal audit alongside two real formula bugs this
file also locks in the fix for:

1. Sortino ratio's downside deviation used to be statistics.stdev() of only the negative
   returns (sample stdev around their own mean, n-1 of the loss subset) instead of the
   standard Sortino & van der Meer downside deviation (sqrt(sum(min(r,0)**2)/N) over ALL N
   returns, measured from 0). The old formula inflated Sortino by 30%+ on a real mixed-sign
   series (hand-verified: 14.76 vs the textbook-correct 11.00 on the same 10 returns).
2. Calmar ratio used raw endpoint-to-endpoint total return despite its own docstring (and its
   caller's) explicitly promising "annualized return / abs(max drawdown)" - most visible during
   the documented ramp-up path (as few as 5 snapshots), where a raw ~1-week return reported as
   "the annualized Calmar ratio" was wrong by roughly 252/n_periods, not a rounding difference.

Expected values below are computed independently (plain arithmetic per each formula's own
docstring), not copied from the implementation, so these tests lock in the methodology rather
than just mirror the code.
"""

import math

import pytest

from utils.metrics_calculator import MetricsCalculator as M


class TestSharpeRatio:
    def test_known_series_matches_hand_computation(self) -> None:
        returns = [0.01, 0.02, -0.01, 0.015, -0.005]
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        std = variance**0.5
        expected = round((mean / std) * (252**0.5), 3)
        assert M.calculate_sharpe_ratio(returns) == expected

    def test_zero_volatility_raises(self) -> None:
        with pytest.raises(ValueError, match="Zero standard deviation"):
            M.calculate_sharpe_ratio([0.01, 0.01, 0.01, 0.01, 0.01])

    def test_insufficient_observations_raises(self) -> None:
        with pytest.raises(ValueError, match="Insufficient data"):
            M.calculate_sharpe_ratio([0.01, 0.02])

    def test_none_returns_raises(self) -> None:
        with pytest.raises(ValueError, match="Insufficient data"):
            M.calculate_sharpe_ratio(None)


class TestSortinoRatioDownsideDeviationFix:
    def test_matches_hand_computed_downside_deviation_over_all_observations(self) -> None:
        returns = [0.02, 0.03, -0.01, -0.02, 0.01, -0.015, 0.025, 0.01, -0.005, 0.015]
        mean = sum(returns) / len(returns)
        downside_dev = math.sqrt(sum(min(r, 0.0) ** 2 for r in returns) / len(returns))
        expected = round((mean / downside_dev) * (252**0.5), 3)
        assert M.calculate_sortino_ratio(returns) == expected

    def test_no_longer_matches_the_old_buggy_negative_only_stdev_formula(self) -> None:
        """Regression guard: the pre-fix formula (stdev of negative returns only, around
        their own mean) must NOT be what this now computes - proves the fix actually changed
        the math, not just the docstring."""
        import statistics

        returns = [0.02, 0.03, -0.01, -0.02, 0.01, -0.015, 0.025, 0.01, -0.005, 0.015]
        mean = statistics.mean(returns)
        old_buggy_downside_std = statistics.stdev([r for r in returns if r < 0])
        old_buggy_sortino = round((mean / old_buggy_downside_std) * (252**0.5), 3)

        result = M.calculate_sortino_ratio(returns)
        assert result != old_buggy_sortino
        assert result == pytest.approx(10.998, abs=0.001)
        assert old_buggy_sortino == pytest.approx(14.756, abs=0.001)

    def test_all_positive_returns_raises_no_downside(self) -> None:
        with pytest.raises(ValueError, match="No downside returns"):
            M.calculate_sortino_ratio([0.01, 0.02, 0.03, 0.01, 0.02])

    def test_all_negative_returns_uses_full_magnitude_not_just_spread(self) -> None:
        """Every return counts toward the downside deviation's sum-of-squares here (matching
        the fixed formula), unlike the old code where downside_std of an all-negative series
        measured only the spread around the (also negative) mean."""
        returns = [-0.01, -0.02, -0.015, -0.01, -0.025]
        mean = sum(returns) / len(returns)
        downside_dev = math.sqrt(sum(r**2 for r in returns) / len(returns))
        expected = round((mean / downside_dev) * (252**0.5), 3)
        assert M.calculate_sortino_ratio(returns) == expected

    def test_insufficient_observations_raises(self) -> None:
        with pytest.raises(ValueError, match="Insufficient data"):
            M.calculate_sortino_ratio([-0.01, 0.02])


class TestMaxDrawdown:
    def test_known_series_matches_hand_computation(self) -> None:
        values = [100.0, 110.0, 90.0, 95.0, 80.0, 120.0]
        # Peak 110 -> trough 80: (110-80)/110*100 = 27.2727...
        assert M.calculate_max_drawdown(values) == round((110.0 - 80.0) / 110.0 * 100, 2)

    def test_monotonically_increasing_returns_zero(self) -> None:
        assert M.calculate_max_drawdown([100.0, 110.0, 120.0, 130.0]) == 0.0

    def test_insufficient_data_raises(self) -> None:
        with pytest.raises(ValueError, match="Insufficient data"):
            M.calculate_max_drawdown([100.0])


class TestCalmarRatioAnnualizationFix:
    def test_full_year_like_series_matches_cagr_annualization(self) -> None:
        """252 daily steps with one mid-series drawdown: annualized_return should equal the
        plain total return raised to the 252/252=1 power - i.e. degenerates to total return
        exactly at n_periods=252, proving the CAGR formula is consistent with the simple case."""
        values = [100.0 * (1.0008**i) for i in range(126)] + [
            100.0 * (1.0008**125) * 0.85 * (1.0008**i) for i in range(127)
        ]
        result = M.calculate_calmar_ratio(values)
        max_dd = M.calculate_max_drawdown(values)
        assert max_dd is not None
        n_periods = len(values) - 1
        annualized_return = ((values[-1] / values[0]) ** (252.0 / n_periods) - 1) * 100
        assert result == round(annualized_return / max_dd, 3)

    def test_short_rampup_window_is_annualized_not_raw_total_return(self) -> None:
        """FIXED: before this fix, a 4-trading-day window's raw ~3% total return would have
        been returned directly and mislabeled 'annualized'. It must now be scaled up via
        252/n_periods, producing a materially larger figure than the raw total return."""
        values = [100.0, 101.0, 100.5, 102.0, 103.0]
        max_dd = M.calculate_max_drawdown(values)
        assert max_dd is not None
        raw_total_return_pct = (values[-1] / values[0] - 1) * 100
        old_buggy_calmar = round(raw_total_return_pct / max_dd, 3)

        result = M.calculate_calmar_ratio(values)
        assert result is not None
        assert result != old_buggy_calmar
        assert result > old_buggy_calmar, "annualizing a short positive-return window must scale it up, not down"

    def test_zero_drawdown_raises(self) -> None:
        with pytest.raises(ValueError, match="max drawdown must be > 0"):
            M.calculate_calmar_ratio([100.0, 110.0, 120.0])

    def test_insufficient_data_raises(self) -> None:
        with pytest.raises(ValueError, match="Insufficient data"):
            M.calculate_calmar_ratio([100.0])


class TestProfitFactor:
    def test_normal_case(self) -> None:
        assert M.calculate_profit_factor(300.0, 100.0) == 3.0

    def test_zero_losses_perfect_record_returns_inf(self) -> None:
        assert M.calculate_profit_factor(100.0, 0.0) == float("inf")

    def test_zero_both_returns_unavailable_marker(self) -> None:
        result = M.calculate_profit_factor(0.0, 0.0)
        assert isinstance(result, dict) and result["data_unavailable"] is True

    def test_missing_data_returns_unavailable_marker(self) -> None:
        result = M.calculate_profit_factor(None, 100.0)
        assert isinstance(result, dict) and result["data_unavailable"] is True


class TestExpectancy:
    def test_known_values_match_hand_computation(self) -> None:
        # 60% win rate, avg win +2.0R, avg loss -1.0R -> 0.6*2.0 - 0.4*1.0 = 0.8
        assert M.calculate_expectancy(60.0, 2.0, -1.0) == 0.8

    def test_positive_avg_loss_takes_absolute_value(self) -> None:
        assert M.calculate_expectancy(60.0, 2.0, 1.0) == M.calculate_expectancy(60.0, 2.0, -1.0)

    def test_missing_input_returns_none(self) -> None:
        assert M.calculate_expectancy(None, 2.0, -1.0) is None


class TestWinRate:
    def test_known_values(self) -> None:
        assert M.calculate_win_rate(100, 60, 40) == 60.0

    def test_zero_total_trades_returns_unavailable_marker(self) -> None:
        result = M.calculate_win_rate(0, 0, 0)
        assert isinstance(result, dict) and result["data_unavailable"] is True

    def test_wins_none_raises(self) -> None:
        with pytest.raises(ValueError, match="wins count is None"):
            M.calculate_win_rate(10, None, 5)


class TestAvgRMultiple:
    def test_known_values(self) -> None:
        assert M.calculate_avg_r_multiple([1.0, -1.0, 2.0, 3.0]) == 1.25

    def test_empty_list_raises(self) -> None:
        with pytest.raises(ValueError, match="no R-multiples"):
            M.calculate_avg_r_multiple([])
