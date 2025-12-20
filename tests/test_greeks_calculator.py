#!/usr/bin/env python3
"""
Unit tests for Black-Scholes Greeks Calculator

Tests the GreeksCalculator class to ensure accurate options Greeks calculations
using the Black-Scholes-Merton model.
"""
import sys
import os
import unittest
import math

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.greeks_calculator import GreeksCalculator


class TestGreeksCalculator(unittest.TestCase):
    """Test cases for Black-Scholes Greeks calculations"""

    def setUp(self):
        """Set up test fixtures"""
        self.calculator = GreeksCalculator()

    # ===== BASIC VALIDATION TESTS =====

    def test_calculate_greeks_call_itm(self):
        """Test call option that is in-the-money (ITM)"""
        greeks = self.calculator.calculate_greeks(
            S=110,     # Stock price
            K=100,     # Strike price
            T=0.25,    # 3 months
            r=0.05,    # 5% risk-free rate
            sigma=0.20,  # 20% volatility
            option_type='call'
        )

        self.assertIsNotNone(greeks)
        self.assertGreater(greeks['delta'], 0.5)  # ITM call has delta > 0.5
        self.assertLess(greeks['delta'], 1.0)
        self.assertGreater(greeks['theta'], -0.1)  # Theta might be negative

    def test_calculate_greeks_call_otm(self):
        """Test call option that is out-of-the-money (OTM)"""
        greeks = self.calculator.calculate_greeks(
            S=90,      # Stock price
            K=100,     # Strike price
            T=0.25,    # 3 months
            r=0.05,
            sigma=0.20,
            option_type='call'
        )

        self.assertIsNotNone(greeks)
        self.assertLess(greeks['delta'], 0.5)  # OTM call has delta < 0.5
        self.assertGreater(greeks['delta'], 0)
        self.assertGreater(greeks['theoretical_value'], 0)

    def test_calculate_greeks_put_itm(self):
        """Test put option that is in-the-money (ITM)"""
        greeks = self.calculator.calculate_greeks(
            S=90,      # Stock price
            K=100,     # Strike price
            T=0.25,
            r=0.05,
            sigma=0.20,
            option_type='put'
        )

        self.assertIsNotNone(greeks)
        self.assertLess(greeks['delta'], -0.5)  # ITM put has delta < -0.5
        self.assertGreater(greeks['delta'], -1.0)

    def test_calculate_greeks_put_otm(self):
        """Test put option that is out-of-the-money (OTM)"""
        greeks = self.calculator.calculate_greeks(
            S=110,     # Stock price
            K=100,     # Strike price
            T=0.25,
            r=0.05,
            sigma=0.20,
            option_type='put'
        )

        self.assertIsNotNone(greeks)
        self.assertGreater(greeks['delta'], -0.5)  # OTM put has delta > -0.5
        self.assertLess(greeks['delta'], 0)

    # ===== EDGE CASE TESTS =====

    def test_calculate_greeks_at_expiration(self):
        """Test option at expiration (T=0)"""
        greeks = self.calculator.calculate_greeks(
            S=110,
            K=100,
            T=0,       # At expiration
            r=0.05,
            sigma=0.20,
            option_type='call'
        )

        self.assertIsNotNone(greeks)
        # At expiration, intrinsic value = max(S-K, 0) for call
        self.assertEqual(greeks['intrinsic_value'], 10)
        # At expiration, extrinsic (time) value = 0
        self.assertEqual(greeks['extrinsic_value'], 0)
        # At expiration, gamma and theta should be 0
        self.assertEqual(greeks['gamma'], 0)
        self.assertEqual(greeks['theta'], 0)

    def test_calculate_greeks_put_at_expiration(self):
        """Test put option at expiration"""
        greeks = self.calculator.calculate_greeks(
            S=90,
            K=100,
            T=0,       # At expiration
            r=0.05,
            sigma=0.20,
            option_type='put'
        )

        self.assertIsNotNone(greeks)
        # At expiration, intrinsic value = max(K-S, 0) for put
        self.assertEqual(greeks['intrinsic_value'], 10)
        self.assertEqual(greeks['extrinsic_value'], 0)

    def test_invalid_inputs_zero_price(self):
        """Test with invalid input: zero stock price"""
        greeks = self.calculator.calculate_greeks(
            S=0,       # Invalid: zero price
            K=100,
            T=0.25,
            r=0.05,
            sigma=0.20,
            option_type='call'
        )

        self.assertIsNone(greeks)  # Should return None for invalid input

    def test_invalid_inputs_zero_volatility(self):
        """Test with invalid input: zero volatility"""
        greeks = self.calculator.calculate_greeks(
            S=100,
            K=100,
            T=0.25,
            r=0.05,
            sigma=0,   # Invalid: zero volatility
            option_type='call'
        )

        self.assertIsNone(greeks)

    def test_invalid_inputs_zero_strike(self):
        """Test with invalid input: zero strike"""
        greeks = self.calculator.calculate_greeks(
            S=100,
            K=0,       # Invalid: zero strike
            T=0.25,
            r=0.05,
            sigma=0.20,
            option_type='call'
        )

        self.assertIsNone(greeks)

    # ===== GREEKS VALUE TESTS =====

    def test_gamma_is_positive(self):
        """Test that gamma is always positive (for both calls and puts)"""
        for option_type in ['call', 'put']:
            greeks = self.calculator.calculate_greeks(
                S=100,
                K=100,
                T=0.25,
                r=0.05,
                sigma=0.20,
                option_type=option_type
            )
            self.assertGreater(greeks['gamma'], 0, f"Gamma should be positive for {option_type}")
            self.assertLess(greeks['gamma'], 1, f"Gamma should be < 1 for {option_type}")

    def test_gamma_symmetry(self):
        """Test that gamma is same for calls and puts at same parameters"""
        greeks_call = self.calculator.calculate_greeks(
            S=100,
            K=100,
            T=0.25,
            r=0.05,
            sigma=0.20,
            option_type='call'
        )

        greeks_put = self.calculator.calculate_greeks(
            S=100,
            K=100,
            T=0.25,
            r=0.05,
            sigma=0.20,
            option_type='put'
        )

        # Gamma should be same for calls and puts
        self.assertAlmostEqual(greeks_call['gamma'], greeks_put['gamma'], places=4)

    def test_theta_is_negative_for_long_options(self):
        """Test that theta is negative (time decay) for long options"""
        for option_type in ['call', 'put']:
            greeks = self.calculator.calculate_greeks(
                S=100,
                K=100,
                T=0.25,
                r=0.05,
                sigma=0.20,
                option_type=option_type
            )
            self.assertLess(greeks['theta'], 0, f"Theta should be negative (time decay) for {option_type}")

    def test_vega_is_positive(self):
        """Test that vega is positive (IV sensitivity)"""
        for option_type in ['call', 'put']:
            greeks = self.calculator.calculate_greeks(
                S=100,
                K=100,
                T=0.25,
                r=0.05,
                sigma=0.20,
                option_type=option_type
            )
            self.assertGreater(greeks['vega'], 0, f"Vega should be positive for {option_type}")

    def test_delta_bounds_call(self):
        """Test that call delta is between 0 and 1"""
        greeks = self.calculator.calculate_greeks(
            S=100,
            K=100,
            T=0.25,
            r=0.05,
            sigma=0.20,
            option_type='call'
        )
        self.assertGreater(greeks['delta'], 0)
        self.assertLess(greeks['delta'], 1)

    def test_delta_bounds_put(self):
        """Test that put delta is between -1 and 0"""
        greeks = self.calculator.calculate_greeks(
            S=100,
            K=100,
            T=0.25,
            r=0.05,
            sigma=0.20,
            option_type='put'
        )
        self.assertGreater(greeks['delta'], -1)
        self.assertLess(greeks['delta'], 0)

    def test_call_put_parity(self):
        """Test put-call parity: C - P = S - K*e^(-rT)"""
        call = self.calculator.calculate_greeks(
            S=100,
            K=100,
            T=0.25,
            r=0.05,
            sigma=0.20,
            option_type='call'
        )

        put = self.calculator.calculate_greeks(
            S=100,
            K=100,
            T=0.25,
            r=0.05,
            sigma=0.20,
            option_type='put'
        )

        # Put-Call Parity: C - P = S - K*e^(-rT)
        expected_diff = 100 - 100 * math.exp(-0.05 * 0.25)
        actual_diff = call['theoretical_value'] - put['theoretical_value']

        # Should be approximately equal (allowing for rounding)
        self.assertAlmostEqual(actual_diff, expected_diff, places=1)

    def test_intrinsic_value_call(self):
        """Test intrinsic value calculation for call"""
        greeks = self.calculator.calculate_greeks(
            S=110,
            K=100,
            T=0.25,
            r=0.05,
            sigma=0.20,
            option_type='call'
        )

        # Intrinsic value = max(S - K, 0) for call
        self.assertEqual(greeks['intrinsic_value'], 10)

    def test_intrinsic_value_put(self):
        """Test intrinsic value calculation for put"""
        greeks = self.calculator.calculate_greeks(
            S=90,
            K=100,
            T=0.25,
            r=0.05,
            sigma=0.20,
            option_type='put'
        )

        # Intrinsic value = max(K - S, 0) for put
        self.assertEqual(greeks['intrinsic_value'], 10)

    def test_extrinsic_value_positive(self):
        """Test that extrinsic value is non-negative"""
        greeks = self.calculator.calculate_greeks(
            S=100,
            K=100,
            T=0.25,
            r=0.05,
            sigma=0.20,
            option_type='call'
        )

        self.assertGreaterEqual(greeks['extrinsic_value'], 0)
        # Extrinsic = Theoretical - Intrinsic
        expected_extrinsic = greeks['theoretical_value'] - greeks['intrinsic_value']
        self.assertAlmostEqual(greeks['extrinsic_value'], expected_extrinsic, places=2)

    # ===== IV RANK TESTS =====

    def test_iv_rank_calculation(self):
        """Test IV percentile rank calculation"""
        # Create at least 30 data points for meaningful IV rank
        iv_history = [0.15 + i * 0.001 for i in range(40)]
        current_iv = 0.24

        iv_rank = self.calculator.calculate_iv_rank(current_iv=current_iv, iv_history=iv_history)

        # 0.24 should rank fairly high in the history
        self.assertIsNotNone(iv_rank)
        self.assertGreater(iv_rank, 50)
        self.assertLessEqual(iv_rank, 100)

    def test_iv_rank_at_minimum(self):
        """Test IV rank when current IV is at minimum"""
        # Need at least 30 data points
        iv_history = [0.15 + i * 0.001 for i in range(40)]
        current_iv = 0.14  # Below all historical values

        iv_rank = self.calculator.calculate_iv_rank(current_iv=current_iv, iv_history=iv_history)

        self.assertAlmostEqual(iv_rank, 0, places=1)  # Should be close to 0%

    def test_iv_rank_at_maximum(self):
        """Test IV rank when current IV is at maximum"""
        # Need at least 30 data points
        iv_history = [0.15 + i * 0.001 for i in range(40)]
        current_iv = 0.25  # Above most historical values

        iv_rank = self.calculator.calculate_iv_rank(current_iv=current_iv, iv_history=iv_history)

        # Should rank high
        self.assertIsNotNone(iv_rank)
        self.assertGreater(iv_rank, 75)

    def test_iv_rank_insufficient_data(self):
        """Test IV rank with insufficient historical data"""
        iv_history = [0.15, 0.16]  # Only 2 data points
        current_iv = 0.20

        iv_rank = self.calculator.calculate_iv_rank(current_iv=current_iv, iv_history=iv_history)

        # Should return None for insufficient data (< 30 points)
        self.assertIsNone(iv_rank)

    def test_iv_rank_empty_history(self):
        """Test IV rank with empty history"""
        iv_rank = self.calculator.calculate_iv_rank(current_iv=0.20, iv_history=[])

        self.assertIsNone(iv_rank)

    # ===== VALIDATION TESTS =====

    def test_validate_greeks_valid(self):
        """Test Greek validation with valid Greeks"""
        greeks = self.calculator.calculate_greeks(
            S=100,
            K=100,
            T=0.25,
            r=0.05,
            sigma=0.20,
            option_type='call'
        )

        is_valid = self.calculator.validate_greeks(greeks)
        self.assertTrue(is_valid)

    def test_validate_greeks_none(self):
        """Test Greek validation with None"""
        is_valid = self.calculator.validate_greeks(None)
        self.assertFalse(is_valid)

    def test_validate_greeks_invalid_delta(self):
        """Test Greek validation with invalid delta"""
        invalid_greeks = {
            'delta': 1.5,  # Invalid: > 1
            'gamma': 0.05,
            'theta': -0.01,
            'vega': 0.1,
            'rho': 0.02,
            'theoretical_value': 2.5,
            'intrinsic_value': 0,
            'extrinsic_value': 2.5
        }

        is_valid = self.calculator.validate_greeks(invalid_greeks)
        self.assertFalse(is_valid)

    # ===== CONVERSION TESTS =====

    def test_days_to_years_conversion(self):
        """Test conversion of days to years"""
        years = self.calculator.days_to_years(365)
        self.assertAlmostEqual(years, 1.0, places=2)

        years = self.calculator.days_to_years(252)  # Trading days
        self.assertAlmostEqual(years, 252/365, places=4)


class TestGreeksCalculatorMoneyness(unittest.TestCase):
    """Test Greeks behavior across moneyness levels"""

    def setUp(self):
        self.calculator = GreeksCalculator()
        self.base_price = 100

    def test_call_delta_progression(self):
        """Test that call delta increases as option becomes more ITM"""
        deltas = []
        for strike in [80, 90, 100, 110, 120]:
            greeks = self.calculator.calculate_greeks(
                S=self.base_price,
                K=strike,
                T=0.25,
                r=0.05,
                sigma=0.20,
                option_type='call'
            )
            deltas.append(greeks['delta'])

        # Deltas should increase as strike decreases (more ITM)
        for i in range(len(deltas) - 1):
            self.assertGreater(deltas[i], deltas[i + 1])

    def test_put_delta_progression(self):
        """Test that put delta becomes more negative as option becomes more ITM"""
        deltas = []
        for strike in [80, 90, 100, 110, 120]:
            greeks = self.calculator.calculate_greeks(
                S=self.base_price,
                K=strike,
                T=0.25,
                r=0.05,
                sigma=0.20,
                option_type='put'
            )
            deltas.append(greeks['delta'])

        # For put options: as strike increases, delta becomes less negative (closer to 0)
        # Because higher strike = further OTM = smaller delta magnitude
        for i in range(len(deltas) - 1):
            self.assertGreater(deltas[i], deltas[i + 1])  # More negative as strike increases


if __name__ == "__main__":
    unittest.main(verbosity=2)
