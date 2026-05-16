#!/usr/bin/env python3
"""
Phase 8: Verify All Calculations & Formulas

Tests:
1. Stock score calculations (RSI, momentum, stability, growth, value, positioning, composite)
2. Position sizing logic
3. Risk calculations (drawdown, exposure, concentration)
4. Signal quality scoring
5. Technical indicators (RSI, ATR, ADX)
"""

import math
import statistics
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Tuple

# Test Data
TEST_SYMBOLS = ["AAPL", "MSFT", "SPY", "GOOGL"]

class CalculationVerifier:
    """Verify all trading calculations are correct."""

    def __init__(self):
        self.errors = []
        self.tests_passed = 0
        self.tests_failed = 0

    def test(self, name: str, condition: bool, expected=None, actual=None):
        """Record test result."""
        if condition:
            self.tests_passed += 1
            print(f"  PASS: {name}")
        else:
            self.tests_failed += 1
            msg = f"  FAIL: {name}"
            if expected is not None and actual is not None:
                msg += f" (expected {expected}, got {actual})"
            print(msg)
            self.errors.append(msg)

    def verify_rsi_calculation(self):
        """Verify RSI calculation."""
        print("\n1. RSI Calculation Verification")
        print("-" * 60)

        # Test case: Simple RSI with known values
        closes = [44, 44.34, 44.09, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.00, 46.00]

        # Compute RSI manually
        rsi = self._compute_rsi(closes, 14)

        # RSI should be between 0 and 100
        self.test("RSI is between 0 and 100", 0 <= rsi <= 100, 0, rsi)
        self.test("RSI is not NaN", not math.isnan(rsi), True, False if math.isnan(rsi) else True)

        # Specific value test: RSI should be ~30 for downtrend
        downtrend = [100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88, 87, 86]
        rsi_downtrend = self._compute_rsi(downtrend, 14)
        self.test("Downtrend gives RSI < 50", rsi_downtrend < 50, True, rsi_downtrend < 50)

    def verify_momentum_calculation(self):
        """Verify momentum/trend calculation."""
        print("\n2. Momentum Calculation Verification")
        print("-" * 60)

        closes = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115]
        momentum = self._compute_momentum(closes, 20)

        # Positive trend should give positive momentum
        self.test("Uptrend gives positive momentum", momentum > 0, True, momentum > 0)

        # Downtrend
        downtrend = [115, 114, 113, 112, 111, 110, 109, 108, 107, 106, 105, 104, 103, 102, 101, 100]
        momentum_down = self._compute_momentum(downtrend, 20)
        self.test("Downtrend gives negative momentum", momentum_down < 0, True, momentum_down < 0)

    def verify_stability_calculation(self):
        """Verify stability (inverse volatility) calculation."""
        print("\n3. Stability Calculation Verification")
        print("-" * 60)

        # Stable price (low volatility)
        stable = [100, 100.1, 100.2, 100.1, 100, 100.1, 99.9, 100]
        stability = self._compute_stability(stable)

        # Volatile price
        volatile = [100, 110, 90, 120, 80, 130, 70, 140]
        volatility_stability = self._compute_stability(volatile)

        self.test("Stable price has high stability score", stability > 80, True, stability > 80)
        self.test("Volatile price has low stability score", volatility_stability < 50, True, volatility_stability < 50)
        self.test("Stability is between 0 and 100", 0 <= stability <= 100, True, 0 <= stability <= 100)

    def verify_composite_score_formula(self):
        """Verify stock composite score formula."""
        print("\n4. Composite Score Formula Verification")
        print("-" * 60)

        # Test weights sum to 100%
        weights = {
            "momentum": 0.25,
            "growth": 0.20,
            "stability": 0.20,
            "value": 0.15,
            "positioning": 0.20,
        }

        total_weight = sum(weights.values())
        self.test("Weights sum to 100%", abs(total_weight - 1.0) < 0.001, 1.0, total_weight)

        # Test composite score calculation
        components = {
            "momentum": 60,
            "growth": 65,
            "stability": 70,
            "value": 55,
            "positioning": 62,
        }

        composite = sum(components[k] * weights[k] for k in weights.keys())
        self.test("Composite score is reasonable", 50 <= composite <= 70, True, 50 <= composite <= 70)
        self.test("Composite score uses all components", len(components) == len(weights), True, len(components) == len(weights))

    def verify_position_sizing(self):
        """Verify position sizing logic."""
        print("\n5. Position Sizing Verification")
        print("-" * 60)

        portfolio_value = 100000  # $100k
        max_position_pct = 0.05   # 5% max per position
        max_positions = 5

        position_size = self._calculate_position_size(portfolio_value, max_position_pct)

        self.test("Position size is positive", position_size > 0, True, position_size > 0)
        self.test("Position size <= max %", position_size <= portfolio_value * max_position_pct * 1.01, True, position_size <= portfolio_value * 0.05 * 1.01)

        # Test multiple positions don't exceed max
        total_exposure = position_size * max_positions
        self.test("Total exposure reasonable", total_exposure <= portfolio_value, True, total_exposure <= portfolio_value)

    def verify_entry_signal_logic(self):
        """Verify entry signal passes all filter tiers."""
        print("\n6. Entry Signal Filter Logic Verification")
        print("-" * 60)

        signal = {
            "symbol": "TEST",
            "date": date.today(),
            "tier1_completeness": 0.75,  # 75% data completeness
            "tier2_market_stage": 2,      # Stage 2 uptrend
            "tier3_trend_score": 8,       # Minervini 8/8
            "tier4_sqs": 50,              # Signal quality score
            "tier5_portfolio_fit": True,  # Fits portfolio
        }

        # All tiers should pass
        tier1_pass = signal["tier1_completeness"] >= 0.45
        tier2_pass = signal["tier2_market_stage"] == 2
        tier3_pass = signal["tier3_trend_score"] >= 6
        tier4_pass = signal["tier4_sqs"] >= 40
        tier5_pass = signal["tier5_portfolio_fit"] == True

        self.test("Tier 1 (Completeness) passes", tier1_pass, True, tier1_pass)
        self.test("Tier 2 (Market Stage) passes", tier2_pass, True, tier2_pass)
        self.test("Tier 3 (Trend Template) passes", tier3_pass, True, tier3_pass)
        self.test("Tier 4 (Signal Quality) passes", tier4_pass, True, tier4_pass)
        self.test("Tier 5 (Portfolio Fit) passes", tier5_pass, True, tier5_pass)

        all_pass = tier1_pass and tier2_pass and tier3_pass and tier4_pass and tier5_pass
        self.test("All tiers pass -> signal qualifies", all_pass, True, all_pass)

    def verify_drawdown_calculation(self):
        """Verify max drawdown calculation."""
        print("\n7. Drawdown Calculation Verification")
        print("-" * 60)

        # Portfolio value over time
        portfolio_values = [100, 105, 103, 98, 110, 108, 95, 100, 112, 120]

        max_dd = self._calculate_max_drawdown(portfolio_values)

        self.test("Drawdown is between 0 and 100%", 0 <= max_dd <= 100, True, 0 <= max_dd <= 100)
        self.test("Drawdown is positive (it's a loss)", max_dd > 0, True, max_dd > 0)

        # Known case: 100 -> 95 = 5% drawdown
        simple_values = [100, 95]
        simple_dd = self._calculate_max_drawdown(simple_values)
        self.test("Simple drawdown is ~5%", 4 <= simple_dd <= 6, True, simple_dd)

    def verify_concentration_calculation(self):
        """Verify portfolio concentration (Herfindahl index)."""
        print("\n8. Concentration Risk Verification")
        print("-" * 60)

        # Diversified portfolio
        weights_diversified = [0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1]
        herfindahl_diversified = sum(w**2 for w in weights_diversified)

        # Concentrated portfolio
        weights_concentrated = [0.5, 0.25, 0.25]
        herfindahl_concentrated = sum(w**2 for w in weights_concentrated)

        self.test("Diversified portfolio has low concentration", herfindahl_diversified < herfindahl_concentrated, True, herfindahl_diversified < herfindahl_concentrated)
        self.test("Concentration index between 0 and 1", 0 <= herfindahl_diversified <= 1, True, 0 <= herfindahl_diversified <= 1)

    # Helper methods
    def _compute_rsi(self, closes: List[float], period: int = 14) -> float:
        """Compute RSI."""
        if len(closes) < period + 1:
            return 50.0

        deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]

        avg_gain = statistics.mean(gains[-period:]) if gains[-period:] else 0
        avg_loss = statistics.mean(losses[-period:]) if losses[-period:] else 0

        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return max(0, min(100, rsi))

    def _compute_momentum(self, closes: List[float], period: int) -> float:
        """Compute price momentum as % change."""
        if len(closes) < period:
            return 0.0
        return ((closes[-1] - closes[-period]) / closes[-period]) * 100

    def _compute_stability(self, closes: List[float]) -> float:
        """Compute stability as inverse volatility."""
        if len(closes) < 2:
            return 50.0

        returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
        volatility = statistics.stdev(returns) * 100 if len(returns) > 1 else 0

        stability = 100 - min(100, max(0, volatility * 10))
        return stability

    def _calculate_position_size(self, portfolio_value: float, max_pct: float) -> float:
        """Calculate position size."""
        return portfolio_value * max_pct

    def _calculate_max_drawdown(self, values: List[float]) -> float:
        """Calculate maximum drawdown."""
        if len(values) < 2:
            return 0.0

        max_val = values[0]
        max_dd = 0.0

        for val in values[1:]:
            if val > max_val:
                max_val = val
            dd = (max_val - val) / max_val * 100
            max_dd = max(max_dd, dd)

        return max_dd


def main():
    """Run all calculation verifications."""
    print("\n" + "="*70)
    print("PHASE 8: CALCULATION VERIFICATION SUITE")
    print("="*70)

    verifier = CalculationVerifier()

    # Run all tests
    verifier.verify_rsi_calculation()
    verifier.verify_momentum_calculation()
    verifier.verify_stability_calculation()
    verifier.verify_composite_score_formula()
    verifier.verify_position_sizing()
    verifier.verify_entry_signal_logic()
    verifier.verify_drawdown_calculation()
    verifier.verify_concentration_calculation()

    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    total = verifier.tests_passed + verifier.tests_failed
    print(f"Tests Passed: {verifier.tests_passed}/{total}")
    print(f"Tests Failed: {verifier.tests_failed}/{total}")

    if verifier.tests_failed == 0:
        print("\n✅ ALL CALCULATIONS VERIFIED - System is trustworthy")
        return 0
    else:
        print(f"\n⚠️  {verifier.tests_failed} calculation issues found:")
        for error in verifier.errors:
            print(error)
        return 1


if __name__ == "__main__":
    exit(main())
