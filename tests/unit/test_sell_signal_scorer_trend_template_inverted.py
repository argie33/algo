#!/usr/bin/env python3
"""Regression test for a 2026-08-10 fix in loaders/signal_quality_scorer.py.

SellSignalScorer.calculate_trend_template_score() was byte-for-byte identical to
BuySignalScorer's version - rewarding a HIGH Minervini score (strong uptrend) and Weinstein
Stage 2/3 (accumulation/advancing) for a SELL signal, exactly backwards for confirming a
bearish breakdown setup. Confirmed live-reachable: buy_sell_daily.signal_type has 34,227 real
'SELL' rows, and load_signal_quality_scores.py dispatches every one of them through
get_signal_scorer('SELL') -> SellSignalScorer.

Fixed to reward Weinstein stage 3/4 (distribution/decline) and a LOW Minervini score (weak
trend template) - the natural inversion of the BUY logic.
"""

from loaders.signal_quality_scorer import BuySignalScorer, SellSignalScorer, get_signal_scorer


class TestSellSignalScorerTrendTemplateInverted:
    def test_sell_scorer_rewards_low_minervini_not_high(self):
        scorer = SellSignalScorer()
        # A weak trend template (bearish confirmation) must score higher than a strong one
        weak_trend_score = scorer.calculate_trend_template_score(minervini=1.0, weinstein_stage=None)
        strong_trend_score = scorer.calculate_trend_template_score(minervini=4.0, weinstein_stage=None)
        assert weak_trend_score > strong_trend_score, (
            f"a SELL signal must score HIGHER on a weak Minervini trend template (bearish "
            f"confirmation), not a strong one - got weak={weak_trend_score}, strong={strong_trend_score}"
        )

    def test_sell_scorer_rewards_distribution_decline_stage_not_advancing(self):
        scorer = SellSignalScorer()
        # Stage 3/4 (distribution/decline) must score higher than Stage 2 (advancing/bullish)
        declining_score = scorer.calculate_trend_template_score(minervini=None, weinstein_stage=3)
        advancing_score = scorer.calculate_trend_template_score(minervini=None, weinstein_stage=2)
        assert declining_score > advancing_score, (
            f"a SELL signal must score HIGHER when the market is in Stage 3/4 "
            f"(distribution/decline), not Stage 2 (advancing) - got decline={declining_score}, "
            f"advancing={advancing_score}"
        )

    def test_sell_scorer_no_longer_identical_to_buy_scorer(self):
        """The core bug: these two must diverge for the same inputs."""
        buy_scorer = BuySignalScorer()
        sell_scorer = SellSignalScorer()
        buy_score = buy_scorer.calculate_trend_template_score(minervini=4.0, weinstein_stage=2)
        sell_score = sell_scorer.calculate_trend_template_score(minervini=4.0, weinstein_stage=2)
        assert buy_score != sell_score, (
            "BUY and SELL trend-template scores must not be identical for a strongly bullish "
            "input (high Minervini, Stage 2) - a SELL signal should score this LOW, not "
            "match the BUY score"
        )

    def test_get_signal_scorer_sell_still_returns_sell_scorer(self):
        """Sanity check: the factory function itself is unaffected by this fix."""
        assert isinstance(get_signal_scorer("SELL"), SellSignalScorer)
        assert isinstance(get_signal_scorer("BUY"), BuySignalScorer)

    def test_sell_score_is_capped_at_25(self):
        scorer = SellSignalScorer()
        score = scorer.calculate_trend_template_score(minervini=0.0, weinstein_stage=4)
        assert score <= 25
