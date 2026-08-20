#!/usr/bin/env python3
"""Signal quality scorer strategy pattern - eliminates switch statements.

Extracted from load_signal_quality_scores.py to eliminate OO abuser code smell.
Responsibility: Calculate quality scores for BUY/SELL signals using strategy pattern.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# Single source of truth for each component's designed point ceiling. Used both to
# clamp individual component scores and to weight the composite (see
# compute_signal_quality_components below). Do not duplicate these numbers elsewhere -
# see loaders/load_signal_quality_scores.py and algo/orchestrator/phase7_signal_generation.py,
# which both call compute_signal_quality_components() rather than recomputing inline.
# History: prior to this consolidation, phase7's inline scorer independently reimplemented
# a 3-of-7-component subset with a raw (non-weighted, non-normalized) sum, silently
# diverging from this formula while its own comment claimed to be "same as batch loader" -
# see git history of this file / phase7_signal_generation.py for the 2026-08-20 fix.
COMPONENT_MAXES: dict[str, int] = {
    "base_quality": 50,
    "volume_confirmation": 20,
    "trend_template": 25,
    "distance_from_high": 15,
    "institutional_ownership": 10,
    "market_stage": 10,
    "vcp_pattern": 10,
}


class SignalQualityScorer(ABC):
    """Base strategy for signal quality scoring."""

    @abstractmethod
    def calculate_base_quality_score(self) -> int:
        """Base quality score (40-60): signal existence + trend alignment."""

    @abstractmethod
    def calculate_volume_confirmation_score(
        self, rsi: float | None, macd: float | None, macd_signal: float | None
    ) -> int:
        """Volume confirmation score (0-20): based on MACD/RSI."""

    @abstractmethod
    def calculate_trend_template_score(self, minervini: float | None, weinstein_stage: int | None) -> int:
        """Trend template score (0-25): minervini score and stage."""


class BuySignalScorer(SignalQualityScorer):
    """Scoring strategy for BUY signals."""

    def calculate_base_quality_score(self) -> int:
        """BUY signals get 50 base points."""
        return 50

    def calculate_volume_confirmation_score(
        self, rsi: float | None, macd: float | None, macd_signal: float | None
    ) -> int:
        """For BUY: RSI 40-80 (+10), MACD > MACD_signal (+10)."""
        score = 0

        if rsi is not None and not pd.isna(rsi):
            rsi_val = float(rsi)
            if 40 < rsi_val < 80:
                score += 10

        if macd is not None and macd_signal is not None and not pd.isna(macd) and not pd.isna(macd_signal):
            if float(macd) > float(macd_signal):
                score += 10

        return score

    def calculate_trend_template_score(self, minervini: float | None, weinstein_stage: int | None) -> int:
        """For BUY: Minervini >= 3 (+15), >= 2 (+10), < 2 (+5); Stage 2/3 (+10), else (+3)."""
        score = 0

        if minervini is not None and not pd.isna(minervini):
            m_val = float(minervini)
            if m_val >= 3:
                score += 15
            elif m_val >= 2:
                score += 10
            else:
                score += 5

        if weinstein_stage is not None and not pd.isna(weinstein_stage):
            stage_val = int(weinstein_stage)
            if stage_val in [2, 3]:
                score += 10
            else:
                score += 3

        return min(25, score)


class SellSignalScorer(SignalQualityScorer):
    """Scoring strategy for SELL signals."""

    def calculate_base_quality_score(self) -> int:
        """SELL signals get 45 base points."""
        return 45

    def calculate_volume_confirmation_score(
        self, rsi: float | None, macd: float | None, macd_signal: float | None
    ) -> int:
        """For SELL: RSI 20-60 (+10), MACD < MACD_signal (+10)."""
        score = 0

        if rsi is not None and not pd.isna(rsi):
            rsi_val = float(rsi)
            if 20 < rsi_val < 60:
                score += 10

        if macd is not None and macd_signal is not None and not pd.isna(macd) and not pd.isna(macd_signal):
            if float(macd) < float(macd_signal):
                score += 10

        return score

    def calculate_trend_template_score(self, minervini: float | None, weinstein_stage: int | None) -> int:
        """For SELL: rewards BEARISH trend confirmation - the inverse of BuySignalScorer.

        BUG FOUND 2026-08-10 (live-reproduced): this was byte-for-byte identical to
        BuySignalScorer.calculate_trend_template_score() - rewarding a HIGH Minervini score
        (strong uptrend) and Weinstein Stage 2/3 (accumulation/advancing) for a SELL signal,
        exactly backwards for confirming a bearish breakdown setup. The prior "Note: SELL
        scoring appears identical to BUY in the original code" comment flagged the smell
        without fixing it. Confirmed reachable, not dead code: buy_sell_daily.signal_type has
        34,227 real 'SELL' rows (vs 28,745 'BUY'), and load_signal_quality_scores.py queries
        `signal_type IN ('BUY', 'SELL')` and dispatches each through get_signal_scorer(),
        so every one of those rows' signal_quality_score was computed with this backwards
        logic. Note: buy_sell_daily.signal (a separate column) is what actually gates real
        entry execution in Phase 7/8 - this system is long-only in practice - so this bug
        doesn't misprice real trades, but it does corrupt signal_quality_score for every SELL
        row, which feeds dashboard/analytics/API consumers (lambda/api/routes/signals.py and
        others) that surface sell-signal quality to an operator.

        Weinstein stage 3/4 (distribution/decline) and a LOW Minervini score (weak trend
        template) are the natural inversion - a stock breaking down while genuinely leaving
        its uptrend, not one still showing bullish trend-template strength.
        """
        score = 0

        if minervini is not None and not pd.isna(minervini):
            m_val = float(minervini)
            if m_val < 2:
                score += 15
            elif m_val < 3:
                score += 10
            else:
                score += 5

        if weinstein_stage is not None and not pd.isna(weinstein_stage):
            stage_val = int(weinstein_stage)
            if stage_val in [3, 4]:
                score += 10
            else:
                score += 3

        return min(25, score)


def get_signal_scorer(signal_type: str) -> SignalQualityScorer:
    """Factory function to get appropriate scorer for signal type."""
    if signal_type == "BUY":
        return BuySignalScorer()
    elif signal_type == "SELL":
        return SellSignalScorer()
    else:
        raise ValueError(f"Unknown signal type: {signal_type}")


def score_distance_from_high(percent_from_52w_high: float | None) -> int:
    """Distance from 52w high score (0-15): closer to the high scores better.

    Always present (never None) - absence of price data resolves to the
    present-but-zero default, same as market_stage below, so it still counts toward
    the composite's denominator (see compute_signal_quality_components).
    """
    if percent_from_52w_high is None:
        return 0
    pct = float(percent_from_52w_high)
    if pd.isna(pct):
        return 0
    if pct >= -5:
        return 15
    elif pct >= -10:
        return 12
    elif pct >= -20:
        return 8
    elif pct >= -30:
        return 4
    return 0


def score_institutional_ownership(institutional_ownership: float | None) -> int | None:
    """Institutional ownership score (0-10). None if genuinely unavailable (excluded from composite)."""
    if institutional_ownership is None or pd.isna(institutional_ownership):
        return None
    io = float(institutional_ownership)
    if io >= 60:
        return 10
    elif io >= 40:
        return 8
    elif io >= 20:
        return 5
    return 2


def score_market_stage(weinstein_stage: int | None) -> int:
    """Market stage score (0-10): Weinstein stage 2/3 (advancing/topping) score best.

    Always present (never None) - same present-but-zero-default reasoning as
    score_distance_from_high.
    """
    if weinstein_stage is None or pd.isna(weinstein_stage):
        return 0
    stage = int(weinstein_stage)
    if stage in (2, 3):
        return 10
    elif stage in (1, 4):
        return 5
    return 2


def score_vcp_pattern(vcp_strength: float | int | None) -> int | None:
    """VCP pattern score (0-10). None if genuinely unavailable (excluded from composite)."""
    if vcp_strength is None or pd.isna(vcp_strength):
        return None
    strength = int(vcp_strength)
    if strength >= 8:
        return 10
    elif strength >= 6:
        return 8
    elif strength >= 4:
        return 5
    return 2


def compute_signal_quality_components(
    signal_type: str,
    rsi: float | None,
    macd: float | None,
    macd_signal: float | None,
    minervini_score: float | None,
    weinstein_stage: int | None,
    percent_from_52w_high: float | None = None,
    institutional_ownership: float | None = None,
    vcp_strength: float | int | None = None,
) -> dict[str, Any]:
    """Single source of truth for signal quality scoring - all 7 components + composite.

    Both loaders/load_signal_quality_scores.py (the batch/EOD path) and
    algo/orchestrator/phase7_signal_generation.py (the live intraday path) call this
    so the score that actually gates trade entry (Phase 8's min_signal_quality_score)
    can never silently diverge from the tested, documented weighting again.

    Composite is a weighted sum of available raw component values over the sum of
    THEIR max values (COMPONENT_MAXES), scaled to 0-100 - NOT an equal-weighted average
    of each component's own percentage, and NOT a raw point-sum clamped at 100. Both of
    those alternatives were shipped and fixed as real bugs previously - see
    tests/unit/test_signal_quality_composite_weighting.py.
    """
    scorer = get_signal_scorer(signal_type)
    base_quality_score = scorer.calculate_base_quality_score()
    volume_confirmation_score = scorer.calculate_volume_confirmation_score(rsi, macd, macd_signal)
    trend_template_score = min(25, scorer.calculate_trend_template_score(minervini_score, weinstein_stage))

    all_components: dict[str, int | None] = {
        "base_quality": base_quality_score,
        "volume_confirmation": volume_confirmation_score,
        "trend_template": trend_template_score,
        "distance_from_high": score_distance_from_high(percent_from_52w_high),
        "institutional_ownership": score_institutional_ownership(institutional_ownership),
        "market_stage": score_market_stage(weinstein_stage),
        "vcp_pattern": score_vcp_pattern(vcp_strength),
    }

    available_maxes = {k: COMPONENT_MAXES[k] for k, v in all_components.items() if v is not None}
    unavailable_components = [k for k, v in all_components.items() if v is None]
    total_max = sum(available_maxes.values())
    composite_sqs = (
        int(sum(v for v in all_components.values() if v is not None) / total_max * 100) if total_max > 0 else 0
    )
    data_completeness = min(99.99, round((len(available_maxes) / len(COMPONENT_MAXES)) * 100, 2))

    return {
        "base_quality_score": int(base_quality_score),
        "volume_confirmation_score": int(volume_confirmation_score),
        "trend_template_score": int(trend_template_score),
        "distance_from_high_score": all_components["distance_from_high"],
        "institutional_ownership_score": all_components["institutional_ownership"],
        "market_stage_score": all_components["market_stage"],
        "vcp_pattern_score": all_components["vcp_pattern"],
        "composite_sqs": composite_sqs,
        "data_completeness": data_completeness,
        "unavailable_components": unavailable_components,
    }
