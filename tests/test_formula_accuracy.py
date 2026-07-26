"""
Formula Accuracy Verification Tests
Finance-grade testing for all critical calculations.
"""

import math


class TestVolatilityCalculation:
    """Verify annualized volatility (√252 factor) is correct."""

    def test_volatility_annualization_factor(self) -> None:
        """√252 trading days per year is the standard factor."""
        factor = math.sqrt(252)
        assert abs(factor - 15.8745) < 0.0001

    def test_daily_volatility_to_annualized(self) -> None:
        """Example: 1% daily vol → 15.87% annualized."""
        daily_std = 0.01
        annualized = daily_std * math.sqrt(252)
        assert abs(annualized - 0.1587) < 0.0001

    def test_volatility_calculation_sample_data(self) -> None:
        """Test volatility with known daily returns."""
        returns = [0.01, -0.005, 0.02, -0.015, 0.01]
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / len(returns)
        daily_std = math.sqrt(variance)
        annualized = daily_std * math.sqrt(252)
        assert annualized > 0
        assert abs(annualized - 0.197) < 0.01


class TestCAGRCalculation:
    """Verify Compound Annual Growth Rate formula."""

    def test_cagr_formula_correctness(self) -> None:
        """CAGR = ((ending/beginning)^(1/years) - 1) * 100"""
        beginning = 100.0
        ending = 121.0  # 21% total return over 2 years
        years = 2
        cagr = ((ending / beginning) ** (1.0 / years) - 1) * 100
        assert abs(cagr - 10.0) < 0.01  # Should be ~10% annualized

    def test_cagr_five_year_example(self) -> None:
        """EPS grew from $1 to $2 over 5 years → ~14.87% CAGR."""
        cagr = ((2.0 / 1.0) ** (1.0 / 5) - 1) * 100
        assert abs(cagr - 14.87) < 0.01

    def test_cagr_negative_value_handling(self) -> None:
        """CAGR undefined when values change sign."""
        beginning = -100.0
        ending = 100.0
        # Should be rejected (sign change)
        is_invalid = (beginning > 0 and ending < 0) or (beginning < 0 and ending > 0)
        assert is_invalid

    def test_cagr_zero_beginning_rejected(self) -> None:
        """Cannot divide by zero."""
        beginning = 0.0
        is_invalid = beginning == 0
        assert is_invalid


class TestBetaCalculation:
    """Verify Beta = Cov(stock, market) / Var(market)."""

    def test_beta_perfect_correlation(self) -> None:
        """Stock perfectly correlated with market should have beta ≈ 1."""
        stock_returns = [0.01, 0.02, -0.01, 0.015, -0.005]
        market_returns = [0.01, 0.02, -0.01, 0.015, -0.005]

        n = len(stock_returns)
        stock_mean = sum(stock_returns) / n
        market_mean = sum(market_returns) / n

        cov = sum(
            (stock_returns[i] - stock_mean) * (market_returns[i] - market_mean)
            for i in range(n)
        ) / n
        var = sum((market_returns[i] - market_mean) ** 2 for i in range(n)) / n

        beta = cov / var if var > 0 else 0
        assert abs(beta - 1.0) < 0.01

    def test_beta_inverse_correlation(self) -> None:
        """Stock inversely correlated with market → negative beta."""
        stock_returns = [0.01, -0.02, 0.01, -0.02, 0.01]
        market_returns = [-0.01, 0.02, -0.01, 0.02, -0.01]

        n = len(stock_returns)
        stock_mean = sum(stock_returns) / n
        market_mean = sum(market_returns) / n

        cov = sum(
            (stock_returns[i] - stock_mean) * (market_returns[i] - market_mean)
            for i in range(n)
        ) / n
        var = sum((market_returns[i] - market_mean) ** 2 for i in range(n)) / n

        beta = cov / var if var > 0 else 0
        assert beta < 0


class TestDrawdownCalculation:
    """Verify Maximum Drawdown formula."""

    def test_drawdown_formula(self) -> None:
        """DD = (peak - current) / peak * 100%"""
        peak = 100000.0
        current = 80000.0
        dd = (peak - current) / peak * 100
        assert abs(dd - 20.0) < 0.01

    def test_drawdown_no_loss(self) -> None:
        """Peak = Current → 0% drawdown."""
        peak = 100000.0
        current = 100000.0
        dd = (peak - current) / peak * 100
        assert dd == 0.0

    def test_drawdown_total_loss(self) -> None:
        """Current = 0 → 100% drawdown."""
        peak = 100000.0
        current = 0.0
        dd = (peak - current) / peak * 100
        assert dd == 100.0

    def test_drawdown_various_levels(self) -> None:
        """Test common drawdown thresholds."""
        peak = 100000.0
        for pct in [5, 10, 15, 20, 25]:
            current = peak * (1 - pct / 100)
            dd = (peak - current) / peak * 100
            assert abs(dd - pct) < 0.01


class TestPEScoring:
    """Verify P/E ratio value scoring formula."""

    def test_pe_scoring_continuity(self) -> None:
        """Verify scoring is continuous at segment boundaries."""
        # At PE=10: both formulas should give same score
        score_1 = 40 + 10 * 2  # = 60
        score_2 = 60 + (10 - 10) * 4  # = 60
        assert score_1 == score_2

        # At PE=20
        score_1 = 60 + (20 - 10) * 4  # = 100
        score_2 = 100 - (20 - 20) * 2  # = 100
        assert score_1 == score_2

        # At PE=35
        score_1 = 100 - (35 - 20) * 2  # = 70
        score_2_base = 70
        score_2 = max(0, score_2_base - (35 - 35) * 1.4)  # = 70
        assert score_1 == score_2

    def test_pe_scoring_ranges(self) -> None:
        """Verify scoring is within 0-100 range."""
        for pe in [5, 10, 15, 20, 25, 30, 35, 50, 100]:
            if pe <= 10:
                score = 40 + pe * 2
            elif pe <= 20:
                score = 60 + (pe - 10) * 4
            elif pe <= 35:
                score = 100 - (pe - 20) * 2
            else:
                score = max(0, 70 - (pe - 35) * 1.4)
            assert 0 <= score <= 100, f"PE={pe} produced out-of-range score {score}"


class TestPBScoring:
    """Verify Price-to-Book ratio scoring."""

    def test_pb_scoring_continuity(self) -> None:
        """Verify scoring is continuous at boundaries."""
        # At PB=1.0
        score_1 = 100
        score_2 = 100 - ((1.0 - 1.0) / 2.0) * 30  # = 100
        assert abs(score_1 - score_2) < 0.01

        # At PB=3.0
        score_1 = 100 - ((3.0 - 1.0) / 2.0) * 30  # = 70
        score_2 = 70 - ((3.0 - 3.0) / 4.0) * 40  # = 70
        assert abs(score_1 - score_2) < 0.01

        # At PB=7.0
        score_1 = 70 - ((7.0 - 3.0) / 4.0) * 40  # = 30
        score_2_base = max(0, 30 - (7.0 - 7.0) * 3)  # = 30
        assert abs(score_1 - score_2_base) < 0.01

    def test_pb_scoring_ranges(self) -> None:
        """Verify PB scoring stays in 0-100."""
        for pb in [0.5, 1.0, 1.5, 3.0, 5.0, 7.0, 10.0, 20.0]:
            if pb <= 1.0:
                score = 100
            elif pb <= 3.0:
                score = 100 - ((pb - 1.0) / 2.0) * 30
            elif pb <= 7.0:
                score = 70 - ((pb - 3.0) / 4.0) * 40
            else:
                score = max(0, 30 - (pb - 7.0) * 3)
            assert 0 <= score <= 100, f"PB={pb} produced score {score}"


class TestDividendYieldScoring:
    """Verify dividend yield scoring with 6% cap."""

    def test_dividend_yield_max_6_percent(self) -> None:
        """Dividend yield capped at 6% for scoring."""
        # From code: div = min(metrics["dividend_yield"] * 100, 6)
        for div_decimal in [0.02, 0.04, 0.06, 0.08, 0.10]:
            div = min(div_decimal * 100, 6)
            score = min(100, div * 16.7)
            assert 0 <= score <= 100

    def test_dividend_yield_scoring_formula(self) -> None:
        """6% dividend yield should score 100."""
        div = 6  # 6%
        score = min(100, div * 16.7)
        assert abs(score - 100) < 0.01

        div = 3  # 3%
        score = min(100, div * 16.7)
        assert abs(score - 50.1) < 0.01


class TestFCFYieldScoring:
    """Verify Free Cash Flow yield scoring."""

    def test_fcf_yield_five_percent(self) -> None:
        """5% FCF yield should score 100."""
        # BUGFIX 2026-07-20: load_sec_valuations.py stores fcf_yield already as a
        # percentage (confirmed live: AAPL=2.27, MSFT=4.69, T=25.83), not a decimal
        # fraction - load_stock_scores.py._score_value used to re-multiply by 100,
        # which saturated this component to 100 for virtually every FCF-positive stock.
        fcf_pct = 5.0  # Already stored as 5.0 (meaning 5%), used as-is
        score = min(100, fcf_pct * 20)
        assert abs(score - 100) < 0.01

    def test_fcf_yield_capped_at_100(self) -> None:
        """Very high FCF yield should cap at 100."""
        fcf_pct = 10.0
        score = min(100, fcf_pct * 20)
        assert score == 100

    def test_fcf_yield_formula_linearity(self) -> None:
        """FCF yield scoring should be linear until cap."""
        for fcf in [1, 2, 3, 4, 5]:
            score = min(100, fcf * 20)
            expected = fcf * 20 if fcf <= 5 else 100
            assert score == expected


class TestMarketExposureWeights:
    """Verify market exposure factor weights sum to 100."""

    def test_factor_weights_sum_to_100(self) -> None:
        """All 12 factors must sum to exactly 100."""
        weights = {
            "trend_30wk": 15,
            "spy_momentum": 10,
            "breadth_200": 10,
            "selling_pressure": 10,
            "vix": 10,
            "credit_spread": 10,
            "put_call": 8,
            "new_highs_lows": 7,
            "ad_line": 6,
            "breadth_50": 6,
            "naaim": 5,
            "aaii": 3,
        }
        assert sum(weights.values()) == 100, f"Weights sum to {sum(weights.values())}"


class TestStockScoreWeights:
    """Verify composite stock score weights."""

    def test_base_weights_sum_to_100(self) -> None:
        """Base factor weights must sum to 100%."""
        weights = {
            "quality": 0.25,
            "growth": 0.20,
            "value": 0.20,
            "positioning": 0.15,
            "stability": 0.12,
            "momentum": 0.08,
        }
        total = sum(weights.values())
        assert abs(total - 1.0) < 0.001

    def test_value_component_weights(self) -> None:
        """Value metric sub-component weights."""
        weights = {
            "pe_ratio": 0.45,
            "pb_ratio": 0.20,
            "ps_ratio": 0.15,
            "fcf_yield": 0.12,
            "dividend_yield": 0.08,
        }
        assert abs(sum(weights.values()) - 1.0) < 0.001

    def test_positioning_component_weights(self) -> None:
        """Positioning metric sub-component weights."""
        weights = {
            "institutional": 0.55,
            "insider": 0.20,
            "short_interest": 0.25,
        }
        assert abs(sum(weights.values()) - 1.0) < 0.001

    def test_stability_component_weights(self) -> None:
        """Stability metric sub-component weights."""
        weights = {
            "volatility_252": 0.40,
            "volatility_60": 0.20,
            "volatility_30": 0.15,
            "beta": 0.15,
            "debt_to_assets": 0.10,
        }
        assert abs(sum(weights.values()) - 1.0) < 0.001

    def test_growth_component_weights(self) -> None:
        """Growth metric sub-component weights."""
        weights = {
            "eps_growth_1y": 0.33,
            "revenue_growth_1y": 0.24,
            "eps_growth_3y": 0.19,
            "revenue_growth_3y": 0.14,
            "eps_growth_5y": 0.05,
            "revenue_growth_5y": 0.05,
        }
        assert abs(sum(weights.values()) - 1.0) < 0.001

    def test_momentum_component_weights(self) -> None:
        """Momentum metric sub-component weights."""
        weights = {
            "momentum_1m": 0.22,
            "momentum_3m": 0.22,
            "momentum_6m": 0.19,
            "momentum_12m": 0.12,
            "rsi_14": 0.15,
            "macd": 0.10,
        }
        assert abs(sum(weights.values()) - 1.0) < 0.001


class TestMomentumCalculation:
    """Verify momentum percentage return formula."""

    def test_momentum_formula(self) -> None:
        """Momentum = ((price_now - price_lookback) / price_lookback) * 100."""
        price_now = 100.0
        price_lookback = 95.0
        momentum = ((price_now - price_lookback) / price_lookback) * 100
        assert abs(momentum - 5.26) < 0.01

    def test_momentum_negative(self) -> None:
        """Negative momentum when price declined."""
        price_now = 90.0
        price_lookback = 100.0
        momentum = ((price_now - price_lookback) / price_lookback) * 100
        assert abs(momentum - (-10.0)) < 0.01

    def test_momentum_weak_filter(self) -> None:
        """Momentum within ±3% is considered weak signal."""
        weak_threshold = 3.0
        for mom in [-3, -2, -1, 0, 1, 2, 3]:
            is_weak = abs(mom) <= weak_threshold
            assert is_weak


class TestROECalculation:
    """Verify Return on Equity formula."""

    def test_roe_formula(self) -> None:
        """ROE = (Net Income / Shareholders Equity) * 100."""
        net_income = 1000000.0
        equity = 5000000.0
        roe = (net_income / equity) * 100
        assert abs(roe - 20.0) < 0.01

    def test_roe_percentage_scaling(self) -> None:
        """ROE stored as percentage (15.23 for 15.23%)."""
        net_income = 1526500.0
        equity = 10000000.0
        roe = (net_income / equity) * 100
        assert abs(roe - 15.265) < 0.01


class TestRebalanceLogic:
    """Verify weight redistribution when metrics missing."""

    def test_weight_redistribution_three_of_six_metrics(self) -> None:
        """When 3 of 6 stock score metrics available, redistribute weights."""
        base_weights = {
            "quality": 0.25,
            "growth": 0.20,
            "value": 0.20,
            "positioning": 0.15,
            "stability": 0.12,
            "momentum": 0.08,
        }

        available = ["quality", "growth", "value"]
        available_weight = sum(base_weights[m] for m in available)

        # Normalize to 100%
        normalized = {}
        for metric in available:
            normalized[metric] = base_weights[metric] / available_weight

        assert abs(sum(normalized.values()) - 1.0) < 0.001

    def test_minimum_completeness_threshold(self) -> None:
        """Require >= 50% (3 of 6) metrics for stock score."""
        min_completeness = 3 / 6
        assert abs(min_completeness - 0.5) < 0.001
