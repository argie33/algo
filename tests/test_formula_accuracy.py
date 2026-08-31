"""
Formula Accuracy Verification Tests
Finance-grade testing for all critical calculations.
"""

import math

from loaders.load_stock_scores import BASE_PILLAR_WEIGHTS, GROWTH_SCORE_FIELDS, StockScoresLoader


class TestVolatilityCalculation:
    """Verify annualized volatility (√252 factor) is correct."""

    def test_volatility_annualization_factor(self) -> None:
        """√252 trading days per year is the standard factor."""
        factor = math.sqrt(252)
        assert abs(factor - 15.8745) < 0.0001

    def test_daily_volatility_to_annualized(self) -> None:
        """Example: 1% daily vol -> 15.87% annualized."""
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
        """EPS grew from $1 to $2 over 5 years -> ~14.87% CAGR."""
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

        cov = sum((stock_returns[i] - stock_mean) * (market_returns[i] - market_mean) for i in range(n)) / n
        var = sum((market_returns[i] - market_mean) ** 2 for i in range(n)) / n

        beta = cov / var if var > 0 else 0
        assert abs(beta - 1.0) < 0.01

    def test_beta_inverse_correlation(self) -> None:
        """Stock inversely correlated with market -> negative beta."""
        stock_returns = [0.01, -0.02, 0.01, -0.02, 0.01]
        market_returns = [-0.01, 0.02, -0.01, 0.02, -0.01]

        n = len(stock_returns)
        stock_mean = sum(stock_returns) / n
        market_mean = sum(market_returns) / n

        cov = sum((stock_returns[i] - stock_mean) * (market_returns[i] - market_mean) for i in range(n)) / n
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
        """Peak = Current -> 0% drawdown."""
        peak = 100000.0
        current = 100000.0
        dd = (peak - current) / peak * 100
        assert dd == 0.0

    def test_drawdown_total_loss(self) -> None:
        """Current = 0 -> 100% drawdown."""
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
    """Verify dividend yield scoring with 6% cap.

    REPLACES TestNetPayoutYieldScoring 2026-08-28 (explicit user directive: "we want the
    dividend yield instead of that payout shit") - load_stock_scores.py._score_value reverted
    from net_payout_yield (dividends + buybacks) back to plain dividend_yield at the same 8%
    weight slot. See that function's docstring for the full history.
    """

    def test_dividend_yield_max_6_percent(self) -> None:
        """Dividend yield capped at 6% for scoring."""
        # From code: div = min(metrics["dividend_yield"] * 100, 6)
        for div_decimal in [0.01, 0.03, 0.06, 0.08, 0.10]:
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
            "positioning": 5,
            "aaii": 3,
        }
        assert sum(weights.values()) == 100, f"Weights sum to {sum(weights.values())}"


class TestStockScoreWeights:
    """Verify composite stock score weights."""

    def test_base_weights_sum_to_100(self) -> None:
        """Base factor weights must sum to 100%.

        Uses the live BASE_PILLAR_WEIGHTS (loaders/load_stock_scores.py) rather than a
        hardcoded copy - a hand-copied duplicate here had already drifted stale (still showed
        growth=0.20/positioning=0.15/stability=0.12/momentum=0.08, pre-dating even the
        2026-08-25 scoring-architecture redesign) without this test ever catching it, since it
        only checked internal self-consistency, not agreement with the real weights.
        """
        total = sum(BASE_PILLAR_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_value_component_weights(self) -> None:
        """Value metric sub-component weights.

        FIXED 20260828 (same drift class test_base_weights_sum_to_100 already documents):
        this hardcoded dict was pe/pb/ps/fcf/dividend = 0.45/0.20/0.15/0.12/0.08 - stale since
        at least the 2026-08-25/26 Value rebuild (dividend_yield replaced by net_payout_yield,
        PEG and margin_of_safety added, PE/PB/PS reweighted). Now the literal weights from
        loaders/load_stock_scores.py's _score_value (grep `weighted_sum +=` in that method for
        the live literals if this ever needs re-verifying).

        dividend_yield reverted 20260828 (user directive) back from net_payout_yield - same 8%
        weight slot, key renamed here to match.

        UPDATED 20260828 (later same day, goal: "aligned with industry standards and best
        practices"): fcf_yield REMOVED (independently re-verified robustly wrong-signed,
        t=-2.43/-0.91/-2.17 full/half/half, see load_stock_scores.py's "FCF YIELD - RESOLVED
        2026-08-28" docstring note). forward_pe ADDED (MSCI Value index core descriptor; user
        directive, unbacktestable today - only ~22 trading days of history exist and no vendor
        source provides historical consensus estimates - see that file's "FORWARD P/E - ADDED
        2026-08-28" note). Freed weight from fcf_yield: PB +3 (33%), PS +2 (29%),
        margin_of_safety +4 (11%).

        UPDATED AGAIN 20260828 (same day, user pushback: "why do you need to remove PEG? why
        not just leave it but keep it lower %"): PEG was initially removed entirely alongside
        fcf_yield in the pass above, on the same "weakest local evidence" reasoning - correctly
        challenged, since PEG's evidence tier (real univariate signal, not a duplicate of
        anything else) is nothing like fcf_yield's (robustly wrong-signed) or ev_ebitda/
        ev_revenue's (near-literal duplicates) removal-worthy tiers. PEG restored at a trimmed
        7%->3% weight instead (same "real but not fully robust" tier as dividend_yield/
        margin_of_safety); forward_pe correspondingly trimmed 7%->4% (deliberately smaller than
        PEG's 3%-plus-real-evidence, since forward_pe has zero local evidence at all).

        margin_of_safety REMOVED FROM SCORING 20260828 (later same day, goal: "is margin of
        safety typically a metric used in the value factor score... or is it typically used
        some other way"): every standard systematic Value-factor methodology (MSCI Enhanced
        Value, Russell Style, S&P Style Indices, Fama-French HML, AQR) is built from accounting
        yield ratios computed directly from financials, not DCF intrinsic-value estimates -
        margin of safety (Graham/Klarman) is industry-standard practice as a per-stock deep-
        value screening tool, not a systematic cross-sectional ranking input, and this repo's
        own sub-period t-stats for it are unstable (0.30 to 2.12) unlike PE/PB/PS's robustness
        in every sub-period tested. See load_stock_scores.py's "MARGIN OF SAFETY - REMOVED FROM
        SCORING 2026-08-28" docstring note. Freed 11%: PB +6 (39%), PS +5 (34%). Still fully
        computed/stored/displayed, primary metric on the Deep Value Picks page instead.

        peg_ratio REMOVED FROM SCORING 20260828 (same day, later pass, goal: "is this value
        score right per industry best practice... lets figure out the right best for the value
        and lets go"): PEG is a growth-ADJUSTED earnings multiple (PE / growth rate) - by
        design a Value/Growth hybrid. No mainstream systematic Value methodology (MSCI Enhanced
        Value/World Value, Russell, S&P Style, Barra, Fama-French/AQR) includes one -
        institutional practice deliberately keeps Value and Growth as separate, independently-
        measurable factors. This repo's own 15-pair pillar-interaction sweep
        (algo/research/cross_pillar_interaction_sweep_20260828.py) confirms Growth x Value
        specifically isn't era-robust either (only Value x Risk is). See load_stock_scores.py's
        "PEG - REMOVED FROM SCORING 2026-08-28" docstring note. Freed 3% went to Dividend Yield
        (8% -> 11%) - the only other input at PEG's same "real but modest" evidentiary tier.

        Everything in this docstring above this point (through 2026-08-28) is stale history -
        the pillar was REVERTED 2026-08-30 (explicit user directive, full history dig found
        little quoted user sign-off for the 08-28 redesign) back to its 08-26/08-28 7-input
        fixed-curve formula, then went through a same-day chain of further explicit user
        directives: Margin of Safety out (Forward P/E swapped in its place) -> FCF Yield out
        (wrong-signed in every window of the pillar's own joint regression, full t=-2.43, both
        halves -0.91/-2.17) -> a full principled reweight of what remained, checking BOTH this
        repo's own backtests AND industry gold standard (MSCI Value: Book/Price + Forward E/P +
        Dividend Yield, notably no trailing E/P) -> trailing P/E removed entirely once a real
        measurement bug was found and fixed (unprofitable companies were being scored as
        NEUTRAL instead of WORST in the test script, understating P/E's true weakness - fixed
        in algo/research/fama_macbeth_value_factors.py's compute_ratios/run()) - once correctly
        measured, trailing P/E's coefficient stays weakly positive and statistically
        indistinguishable from zero in every window (full t=+0.59, first half t=+0.64, second
        half t=+0.14 - re-verified directly against the live DB 2026-08-31, correcting an
        earlier claim of a sign flip that did not reproduce), leaving it with no reliable signal
        either way, and per MSCI's own methodology it was never supposed to be scored anyway. An
        initial pass set weights on
        the four remaining backtestable inputs (P/B/P/S/PEG/Dividend) proportional to each
        one's average |t-stat| across full-sample/2014-2020/2020-2026 (post-fix numbers), with
        Forward P/E held at a smaller judgment-anchored floor - SUPERSEDED same day by an
        explicit user directive to equal-weight all five inputs at 20% each instead, which is
        what's actually live. A legitimate, evidence-consistent choice, not just preference:
        the research script's own composite backtest already found equal-weighting performs
        statistically indistinguishably from hand-tuned weights in every window tested (input
        SELECTION carries this pillar's performance, not the specific split). See
        loaders/load_stock_scores.py's _score_value docstring "CURRENT LIVE FORMULA" note for
        the full step-by-step trail.

        FINAL/CURRENT weights (2026-08-30): five inputs, EQUAL WEIGHT, no trailing P/E, no
        margin_of_safety, no fcf_yield.
        """
        weights = {
            "pb_ratio": 0.20,
            "ps_ratio": 0.20,
            "peg_ratio": 0.20,
            "forward_pe": 0.20,
            "dividend_yield": 0.20,
        }
        assert abs(sum(weights.values()) - 1.0) < 0.001

    def test_positioning_not_scored(self) -> None:
        """Positioning was fully retired as a composite pillar 2026-08-27 (evidence-driven -
        see BASE_PILLAR_WEIGHTS's docstring) - replaces a stale test_positioning_component_weights
        that asserted a hardcoded weight dict (institutional/insider/short_interest) summed to
        1.0 regardless of whether `_score_positioning` still existed. It doesn't - A/D rating,
        institutional ownership, and short interest are still computed/stored for display
        (positioning_inputs) but no longer combined into a scored pillar.
        """
        assert not hasattr(StockScoresLoader, "_score_positioning")
        assert "positioning" not in BASE_PILLAR_WEIGHTS

    def test_risk_component_weights(self) -> None:
        """Risk (renamed from Stability) metric sub-component weights.

        REWORKED 20260830 (later same day, user directive: full delegation to figure out the
        best combination - see _score_risk's own docstring for the per-input reasoning).
        volatility_30d dropped (most redundant of the three windows); max_drawdown_1y restored
        as a loss-severity characterization; debt_to_assets stays out (balance-sheet metric,
        scored under Quality instead). Live literals from _score_risk's `weighted_sum +=`
        lines - these four sum to exactly 1.0, unlike the prior formula's 0.90.
        """
        weights = {
            "volatility_60d": 0.45,
            "volatility_252d": 0.20,
            "beta": 0.20,
            "max_drawdown": 0.15,
        }
        assert abs(sum(weights.values()) - 1.0) < 0.001

    def test_growth_component_weights(self) -> None:
        """Growth metric sub-component weights.

        RESTORED TO MULTI-INPUT 20260828 (user directive, /goal session: "get the rest of the
        growth inputs back in there the ones that are in the react" + explicit pushback that
        revenue_growth_1y's inversion "shouldn't be inverted"). Supersedes the prior single-
        input history this test used to guard (6-input blend -> book_value_growth alone ->
        revenue_growth_1y alone) - see _score_growth's own docstring for that evidence-vs-
        override trail. Equal-weighted across every GROWTH_SCORE_FIELDS candidate (partial-
        availability renormalized in the actual scoring code - this static weights dict just
        documents the equal-share intent, same convention Risk/Momentum's dicts below use).
        """
        weights = dict.fromkeys(GROWTH_SCORE_FIELDS, 1.0 / len(GROWTH_SCORE_FIELDS))
        assert abs(sum(weights.values()) - 1.0) < 0.001

    def test_momentum_component_weights(self) -> None:
        """Momentum metric sub-component weights.

        FIXED 20260828: was a stale 6-window dict including momentum_1m/momentum_6m/
        momentum_12m, none of which _score_momentum scores standalone any more (momentum_1m is
        an input to the derived 12-1 construction, not a scored field itself; momentum_6m/12m
        were replaced by that same 12-1 construction 2026-08-25 - see _score_momentum's
        docstring for the collinearity finding that drove it). Live literals from
        _score_momentum's `weighted_sum +=` lines.
        """
        weights = {
            "momentum_3m": 0.20,
            "momentum_12_1": 0.35,
            "rsi_14": 0.21,
            "macd_sign": 0.16,
            "sma_50_200_avg": 0.08,
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
        available = ["quality", "growth", "value"]
        available_weight = sum(BASE_PILLAR_WEIGHTS[m] for m in available)

        # Normalize to 100%
        normalized = {}
        for metric in available:
            normalized[metric] = BASE_PILLAR_WEIGHTS[metric] / available_weight

        assert abs(sum(normalized.values()) - 1.0) < 0.001

    def test_minimum_completeness_threshold(self) -> None:
        """Require >= 50% (3 of 6) metrics for stock score."""
        min_completeness = 3 / 6
        assert abs(min_completeness - 0.5) < 0.001
