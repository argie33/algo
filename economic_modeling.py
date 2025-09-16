#!/usr/bin/env python3
"""
Economic Modeling Framework - Recession Prediction System
Based on academic research and proven economic indicators
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
import yfinance as yf


@dataclass
class EconomicIndicator:
    name: str
    value: float
    signal_strength: float  # 0-1 scale
    last_updated: datetime
    historical_average: float
    current_percentile: float


class BaseIndicator(ABC):
    """Base class for economic indicators"""

    @abstractmethod
    def get_current_value(self) -> EconomicIndicator:
        pass

    @abstractmethod
    def calculate_signal_strength(self, current_value: float) -> float:
        pass


class YieldCurveIndicator(BaseIndicator):
    """
    Yield Curve Inversion Indicator
    Based on Estrella & Mishkin (1998) research
    """

    def __init__(self):
        self.name = "Yield Curve (10Y-2Y)"
        self.fred_api_key = None  # Set your FRED API key

    def get_current_value(self) -> EconomicIndicator:
        # Fetch 10Y and 2Y Treasury yields using yfinance
        try:
            # 10-Year Treasury
            ten_year = yf.Ticker("^TNX")
            ten_year_data = ten_year.history(period="5d")
            current_10y = ten_year_data["Close"].iloc[-1] / 100

            # 2-Year Treasury
            two_year = yf.Ticker("^IRX")
            two_year_data = two_year.history(period="5d")
            current_2y = two_year_data["Close"].iloc[-1] / 100

            spread = current_10y - current_2y
            signal_strength = self.calculate_signal_strength(spread)

            return EconomicIndicator(
                name=self.name,
                value=spread,
                signal_strength=signal_strength,
                last_updated=datetime.now(),
                historical_average=0.015,  # 1.5% historical average
                current_percentile=self._calculate_percentile(spread),
            )
        except Exception as e:
            print(f"Error fetching yield curve data: {e}")
            return EconomicIndicator(
                name=self.name,
                value=0.0,
                signal_strength=0.0,
                last_updated=datetime.now(),
                historical_average=0.015,
                current_percentile=50.0,
            )

    def calculate_signal_strength(self, spread: float) -> float:
        """
        Calculate recession signal strength based on yield curve spread
        Negative spread indicates higher recession probability
        """
        if spread < -0.005:  # Significant inversion
            return min(1.0, abs(spread) * 20)  # Scale to 0-1
        elif spread < 0:  # Mild inversion
            return abs(spread) * 10
        else:  # Normal curve
            return max(0.0, 1.0 - spread * 5)  # Lower signal as spread increases

    def _calculate_percentile(self, current_spread: float) -> float:
        """Calculate current spread percentile vs historical data"""
        # Simplified percentile calculation
        # In production, use historical data
        if current_spread < -0.01:
            return 95.0  # Very high recession signal
        elif current_spread < 0:
            return 70.0
        elif current_spread < 0.01:
            return 40.0
        else:
            return 20.0


class CreditSpreadIndicator(BaseIndicator):
    """
    Credit Spread Indicator
    Based on Gilchrist & Zakrajšek (2012) research
    """

    def __init__(self):
        self.name = "Credit Spreads (HYG-Treasury)"

    def get_current_value(self) -> EconomicIndicator:
        try:
            # High Yield Bond ETF (HYG) as proxy for credit spreads
            hyg = yf.Ticker("HYG")
            hyg_data = hyg.history(period="5d")

            # Treasury ETF (IEF) as risk-free proxy
            ief = yf.Ticker("IEF")
            ief_data = ief.history(period="5d")

            # Calculate yield spread approximation
            hyg_return = (hyg_data["Close"].iloc[-1] / hyg_data["Close"].iloc[0]) - 1
            ief_return = (ief_data["Close"].iloc[-1] / ief_data["Close"].iloc[0]) - 1

            spread_proxy = hyg_return - ief_return
            signal_strength = self.calculate_signal_strength(spread_proxy)

            return EconomicIndicator(
                name=self.name,
                value=spread_proxy,
                signal_strength=signal_strength,
                last_updated=datetime.now(),
                historical_average=0.0,
                current_percentile=self._calculate_percentile(spread_proxy),
            )
        except Exception as e:
            print(f"Error fetching credit spread data: {e}")
            return EconomicIndicator(
                name=self.name,
                value=0.0,
                signal_strength=0.0,
                last_updated=datetime.now(),
                historical_average=0.0,
                current_percentile=50.0,
            )

    def calculate_signal_strength(self, spread: float) -> float:
        """Credit stress increases recession probability"""
        if spread < -0.05:  # Significant credit stress
            return min(1.0, abs(spread) * 10)
        elif spread < -0.02:  # Moderate stress
            return abs(spread) * 5
        else:  # Normal conditions
            return 0.0

    def _calculate_percentile(self, spread: float) -> float:
        if spread < -0.05:
            return 90.0
        elif spread < -0.02:
            return 70.0
        else:
            return 30.0


class EmploymentIndicator(BaseIndicator):
    """
    Employment Leading Indicator (Sahm Rule)
    Based on Claudia Sahm's research
    """

    def __init__(self):
        self.name = "Employment (Sahm Rule)"

    def get_current_value(self) -> EconomicIndicator:
        # Simplified implementation - would use FRED API in production
        # Sahm Rule: Recession when 3-month moving average of unemployment rate
        # rises by 0.5+ percentage points from its low over prior 12 months

        try:
            # Placeholder implementation
            sahm_value = 0.2  # Would calculate from actual unemployment data
            signal_strength = self.calculate_signal_strength(sahm_value)

            return EconomicIndicator(
                name=self.name,
                value=sahm_value,
                signal_strength=signal_strength,
                last_updated=datetime.now(),
                historical_average=0.0,
                current_percentile=40.0,
            )
        except Exception as e:
            print(f"Error calculating employment indicator: {e}")
            return EconomicIndicator(
                name=self.name,
                value=0.0,
                signal_strength=0.0,
                last_updated=datetime.now(),
                historical_average=0.0,
                current_percentile=50.0,
            )

    def calculate_signal_strength(self, sahm_value: float) -> float:
        """Sahm Rule triggers at 0.5"""
        if sahm_value >= 0.5:
            return 1.0  # Recession signal triggered
        elif sahm_value >= 0.3:
            return sahm_value * 2  # Building signal
        else:
            return 0.0


class ConsumerSentimentIndicator(BaseIndicator):
    """
    Consumer Sentiment Indicator
    University of Michigan Consumer Sentiment
    """

    def __init__(self):
        self.name = "Consumer Sentiment"

    def get_current_value(self) -> EconomicIndicator:
        # Placeholder - would integrate with University of Michigan data
        sentiment_value = 85.0  # Index value
        signal_strength = self.calculate_signal_strength(sentiment_value)

        return EconomicIndicator(
            name=self.name,
            value=sentiment_value,
            signal_strength=signal_strength,
            last_updated=datetime.now(),
            historical_average=90.0,
            current_percentile=45.0,
        )

    def calculate_signal_strength(self, sentiment: float) -> float:
        """Low sentiment indicates recession risk"""
        if sentiment < 70:
            return 0.8
        elif sentiment < 80:
            return 0.5
        elif sentiment < 90:
            return 0.2
        else:
            return 0.0


class LEIIndicator(BaseIndicator):
    """
    Leading Economic Indicators
    Conference Board Leading Economic Index
    """

    def __init__(self):
        self.name = "Leading Economic Indicators"

    def get_current_value(self) -> EconomicIndicator:
        # Placeholder implementation
        lei_change = -0.3  # 3-month change in LEI
        signal_strength = self.calculate_signal_strength(lei_change)

        return EconomicIndicator(
            name=self.name,
            value=lei_change,
            signal_strength=signal_strength,
            last_updated=datetime.now(),
            historical_average=0.1,
            current_percentile=30.0,
        )

    def calculate_signal_strength(self, lei_change: float) -> float:
        """Declining LEI indicates recession risk"""
        if lei_change < -0.5:
            return 0.8
        elif lei_change < -0.2:
            return 0.5
        elif lei_change < 0:
            return 0.2
        else:
            return 0.0


class RecessionPredictor:
    """
    Multi-factor recession prediction model based on academic research

    Indicators Based on:
    - Yield Curve Inversion (Estrella & Mishkin, 1998)
    - Credit Spreads (Gilchrist & Zakrajšek, 2012)
    - Employment Leading Indicators (Sahm Rule)
    - Consumer Sentiment (University of Michigan)
    """

    def __init__(self):
        self.indicators = {
            "yield_curve": YieldCurveIndicator(),
            "credit_spreads": CreditSpreadIndicator(),
            "employment": EmploymentIndicator(),
            "consumer_sentiment": ConsumerSentimentIndicator(),
            "leading_indicators": LEIIndicator(),
        }

        # Research-based weights
        self.weights = {
            "yield_curve": 0.30,  # Strongest predictor historically
            "credit_spreads": 0.25,  # Financial stress indicator
            "employment": 0.20,  # Real economy indicator
            "consumer_sentiment": 0.15,  # Forward-looking behavior
            "leading_indicators": 0.10,  # Composite indicator
        }

    def calculate_recession_probability(self) -> Dict:
        """Calculate comprehensive recession probability"""
        # Get current indicator values
        indicator_values = {}
        indicator_details = {}

        for name, indicator in self.indicators.items():
            current_indicator = indicator.get_current_value()
            indicator_values[name] = current_indicator.signal_strength
            indicator_details[name] = current_indicator

        # Calculate weighted probability
        recession_prob = sum(
            indicator_values[name] * self.weights[name] for name in indicator_values
        )

        # Determine risk level
        risk_level = self._determine_risk_level(recession_prob)

        # Identify key risks
        key_risks = self._identify_key_risks(indicator_details)

        return {
            "probability": min(1.0, recession_prob),
            "risk_level": risk_level,
            "confidence_interval": self._calculate_confidence_interval(recession_prob),
            "time_horizon": "6-12 months",
            "key_risks": key_risks,
            "indicator_breakdown": {
                name: {
                    "value": details.value,
                    "signal_strength": details.signal_strength,
                    "weight": self.weights[name],
                    "contribution": details.signal_strength * self.weights[name],
                }
                for name, details in indicator_details.items()
            },
            "last_updated": datetime.now(),
        }

    def _determine_risk_level(self, probability: float) -> str:
        """Determine qualitative risk level"""
        if probability >= 0.7:
            return "HIGH"
        elif probability >= 0.4:
            return "MODERATE"
        elif probability >= 0.2:
            return "LOW"
        else:
            return "MINIMAL"

    def _calculate_confidence_interval(self, probability: float) -> Tuple[float, float]:
        """Calculate confidence interval for probability estimate"""
        # Simplified confidence interval calculation
        margin = 0.15 * (1 - abs(probability - 0.5) * 2)  # Higher uncertainty near 0.5
        lower = max(0.0, probability - margin)
        upper = min(1.0, probability + margin)
        return (lower, upper)

    def _identify_key_risks(
        self, indicators: Dict[str, EconomicIndicator]
    ) -> List[str]:
        """Identify the most concerning indicators"""
        risks = []

        for name, indicator in indicators.items():
            if indicator.signal_strength >= 0.6:
                if name == "yield_curve":
                    risks.append("Yield curve inversion signaling credit tightening")
                elif name == "credit_spreads":
                    risks.append(
                        "Credit market stress indicating financial instability"
                    )
                elif name == "employment":
                    risks.append("Labor market deterioration (Sahm Rule activation)")
                elif name == "consumer_sentiment":
                    risks.append("Consumer confidence collapse")
                elif name == "leading_indicators":
                    risks.append("Leading economic indicators declining")

        if not risks:
            risks.append("No major recession signals detected")

        return risks


class MarketRegimeDetector:
    """
    Detect current market regime (Bull/Bear/Normal)
    Used for dynamic scoring weight adjustment
    """

    def __init__(self):
        self.lookback_periods = {
            "short": 63,  # ~3 months
            "medium": 126,  # ~6 months
            "long": 252,  # ~1 year
        }

    def detect_regime(self) -> Dict:
        """Detect current market regime"""
        try:
            # Use S&P 500 as market proxy
            sp500 = yf.Ticker("^GSPC")
            data = sp500.history(period="1y")

            # Calculate returns
            returns = data["Close"].pct_change().dropna()

            # Calculate regime indicators
            regime_indicators = {}

            for period_name, period_days in self.lookback_periods.items():
                period_returns = returns.tail(period_days)

                regime_indicators[f"{period_name}_return"] = period_returns.mean() * 252
                regime_indicators[f"{period_name}_volatility"] = (
                    period_returns.std() * np.sqrt(252)
                )
                regime_indicators[f"{period_name}_sharpe"] = (
                    regime_indicators[f"{period_name}_return"]
                    / regime_indicators[f"{period_name}_volatility"]
                )

            # Determine regime
            regime = self._classify_regime(regime_indicators)

            return {
                "regime": regime,
                "confidence": self._calculate_regime_confidence(regime_indicators),
                "indicators": regime_indicators,
                "last_updated": datetime.now(),
            }

        except Exception as e:
            print(f"Error detecting market regime: {e}")
            return {
                "regime": "normal",
                "confidence": 0.5,
                "indicators": {},
                "last_updated": datetime.now(),
            }

    def _classify_regime(self, indicators: Dict) -> str:
        """Classify market regime based on indicators"""
        short_return = indicators.get("short_return", 0)
        medium_return = indicators.get("medium_return", 0)
        long_return = indicators.get("long_return", 0)

        short_vol = indicators.get("short_volatility", 0.2)

        # Bull market criteria
        if (
            short_return > 0.1
            and medium_return > 0.05
            and long_return > 0.0
            and short_vol < 0.25
        ):
            return "bull"

        # Bear market criteria
        elif short_return < -0.1 and medium_return < -0.05 and short_vol > 0.3:
            return "bear"

        # Normal market
        else:
            return "normal"

    def _calculate_regime_confidence(self, indicators: Dict) -> float:
        """Calculate confidence in regime classification"""
        # Simplified confidence calculation
        short_return = abs(indicators.get("short_return", 0))
        volatility = indicators.get("short_volatility", 0.2)

        # Higher confidence for more extreme conditions
        return min(1.0, (short_return + volatility) / 0.5)


def main():
    """Example usage of the economic modeling framework"""
    print("Economic Modeling Framework - Recession Prediction")
    print("=" * 50)

    # Initialize recession predictor
    predictor = RecessionPredictor()

    # Calculate recession probability
    result = predictor.calculate_recession_probability()

    print(f"Recession Probability: {result['probability']:.1%}")
    print(f"Risk Level: {result['risk_level']}")
    print(f"Time Horizon: {result['time_horizon']}")
    print(
        f"Confidence Interval: {result['confidence_interval'][0]:.1%} - {result['confidence_interval'][1]:.1%}"
    )

    print("\nIndicator Breakdown:")
    for name, details in result["indicator_breakdown"].items():
        print(
            f"  {name}: {details['signal_strength']:.2f} (weight: {details['weight']:.1%}, contribution: {details['contribution']:.3f})"
        )

    print(f"\nKey Risks:")
    for risk in result["key_risks"]:
        print(f"  - {risk}")

    print("\n" + "=" * 50)

    # Market regime detection
    regime_detector = MarketRegimeDetector()
    regime_result = regime_detector.detect_regime()

    print(f"Market Regime: {regime_result['regime'].upper()}")
    print(f"Confidence: {regime_result['confidence']:.1%}")

    if regime_result["indicators"]:
        print("\nRegime Indicators:")
        for indicator, value in regime_result["indicators"].items():
            if "return" in indicator:
                print(f"  {indicator}: {value:.1%}")
            elif "volatility" in indicator:
                print(f"  {indicator}: {value:.1%}")
            elif "sharpe" in indicator:
                print(f"  {indicator}: {value:.2f}")


if __name__ == "__main__":
    main()
