#!/usr/bin/env python3
"""Signal quality scorer strategy pattern - eliminates switch statements.

Extracted from load_signal_quality_scores.py to eliminate OO abuser code smell.
Responsibility: Calculate quality scores for BUY/SELL signals using strategy pattern.
"""

import logging
from abc import ABC, abstractmethod

import pandas as pd

logger = logging.getLogger(__name__)


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
        """For SELL: Similar to BUY (uses same scoring rules)."""
        # Note: SELL scoring appears identical to BUY in the original code
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


def get_signal_scorer(signal_type: str) -> SignalQualityScorer:
    """Factory function to get appropriate scorer for signal type."""
    if signal_type == "BUY":
        return BuySignalScorer()
    elif signal_type == "SELL":
        return SellSignalScorer()
    else:
        raise ValueError(f"Unknown signal type: {signal_type}")
