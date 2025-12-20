#!/usr/bin/env python3
"""
Black-Scholes Greeks Calculator
Calculates option Greeks using the Black-Scholes-Merton model.

Greeks calculated:
- Delta: Rate of change of option price with respect to stock price
- Gamma: Rate of change of delta with respect to stock price
- Theta: Rate of change of option price with respect to time (daily decay)
- Vega: Rate of change of option price with respect to implied volatility
- Rho: Rate of change of option price with respect to interest rate

Also calculates:
- Theoretical option value
- Intrinsic value
- Extrinsic (time) value
- IV percentile rank vs historical data
"""
import numpy as np
from scipy.stats import norm
import logging

logger = logging.getLogger(__name__)


class GreeksCalculator:
    """Calculate Black-Scholes Greeks for options"""

    @staticmethod
    def calculate_greeks(S, K, T, r, sigma, option_type='call'):
        """
        Calculate all Greeks for an option using Black-Scholes formula.

        Parameters:
        -----------
        S : float
            Current stock price
        K : float
            Strike price
        T : float
            Time to expiration (in years). Use (expiration_date - today).days / 365.0
        r : float
            Risk-free rate (annual, as decimal). Example: 0.045 for 4.5%
        sigma : float
            Implied volatility (annual, as decimal). Example: 0.25 for 25%
        option_type : str
            'call' or 'put'

        Returns:
        --------
        dict with keys:
            - delta: Hedge ratio (0-1 for calls, -1-0 for puts)
            - gamma: Delta sensitivity to stock price changes
            - theta: Daily time decay (negative for long options)
            - vega: Sensitivity to 1% change in IV (per 1% IV change)
            - rho: Sensitivity to 1% change in interest rate
            - theoretical_value: Model price of option
            - intrinsic_value: Value at expiration
            - extrinsic_value: Time value (theoretical - intrinsic)

        Example:
        --------
        >>> greeks = GreeksCalculator.calculate_greeks(
        ...     S=100, K=105, T=0.25, r=0.05, sigma=0.20, option_type='call'
        ... )
        >>> print(f"Delta: {greeks['delta']}, Theta: {greeks['theta']}")
        """

        # Handle edge case: at or past expiration
        if T <= 0:
            intrinsic = max(S - K, 0) if option_type == 'call' else max(K - S, 0)
            return {
                'delta': 1.0 if (option_type == 'call' and S > K) else 0.0,
                'gamma': 0.0,
                'theta': 0.0,
                'vega': 0.0,
                'rho': 0.0,
                'theoretical_value': intrinsic,
                'intrinsic_value': intrinsic,
                'extrinsic_value': 0.0
            }

        try:
            # Validate inputs
            if S <= 0 or K <= 0 or sigma <= 0:
                logger.warning(
                    f"Invalid inputs: S={S}, K={K}, sigma={sigma}. "
                    f"All must be positive."
                )
                return None

            # Calculate d1 and d2 (core of Black-Scholes)
            d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
            d2 = d1 - sigma * np.sqrt(T)

            # Standard normal CDF and PDF values
            N_d1 = norm.cdf(d1)
            N_d2 = norm.cdf(d2)
            N_neg_d1 = norm.cdf(-d1)
            N_neg_d2 = norm.cdf(-d2)
            n_d1 = norm.pdf(d1)  # Standard normal PDF

            # Calculate option price
            if option_type == 'call':
                price = S * N_d1 - K * np.exp(-r * T) * N_d2
                delta = N_d1
                rho = K * T * np.exp(-r * T) * N_d2 / 100
                intrinsic = max(S - K, 0)
            else:  # put
                price = K * np.exp(-r * T) * N_neg_d2 - S * N_neg_d1
                delta = -N_neg_d1
                rho = -K * T * np.exp(-r * T) * N_neg_d2 / 100
                intrinsic = max(K - S, 0)

            # Greeks same for both calls and puts
            gamma = n_d1 / (S * sigma * np.sqrt(T))

            # Vega: per 1% change in IV
            vega = S * n_d1 * np.sqrt(T) / 100

            # Theta: per day (divide annual by 365)
            if option_type == 'call':
                theta = (
                    -(S * n_d1 * sigma) / (2 * np.sqrt(T))
                    - r * K * np.exp(-r * T) * N_d2
                ) / 365
            else:  # put
                theta = (
                    -(S * n_d1 * sigma) / (2 * np.sqrt(T))
                    + r * K * np.exp(-r * T) * N_neg_d2
                ) / 365

            extrinsic = price - intrinsic

            return {
                'delta': round(float(delta), 4),
                'gamma': round(float(gamma), 4),
                'theta': round(float(theta), 4),
                'vega': round(float(vega), 4),
                'rho': round(float(rho), 4),
                'theoretical_value': round(float(price), 2),
                'intrinsic_value': round(float(intrinsic), 2),
                'extrinsic_value': round(float(extrinsic), 2)
            }

        except Exception as e:
            logger.error(
                f"Error calculating Greeks for S={S}, K={K}, T={T}, "
                f"r={r}, sigma={sigma}: {e}"
            )
            return None

    @staticmethod
    def calculate_iv_rank(current_iv, iv_history):
        """
        Calculate IV percentile rank compared to historical IV.

        IV Rank shows where current IV stands relative to past IV:
        - 100% = IV at highest point in period
        - 0% = IV at lowest point in period
        - 50% = IV at median

        Parameters:
        -----------
        current_iv : float
            Current implied volatility (decimal, e.g., 0.25 for 25%)
        iv_history : list
            List of historical IV values (e.g., last 252 trading days)

        Returns:
        --------
        float : IV percentile rank (0-100), or None if insufficient data
        """

        if not iv_history or len(iv_history) < 30:
            # Need at least 30 data points for meaningful percentile
            return None

        try:
            # Count how many historical IVs are below current IV
            below_current = sum(1 for iv in iv_history if iv < current_iv)

            # Calculate percentile (0-100)
            percentile = (below_current / len(iv_history)) * 100

            return round(percentile, 1)

        except Exception as e:
            logger.error(f"Error calculating IV rank: {e}")
            return None

    @staticmethod
    def days_to_years(days):
        """Convert days to years for use in Greeks calculations."""
        return days / 365.0

    @staticmethod
    def validate_greeks(greeks):
        """
        Sanity check Greeks values.

        Returns True if Greeks appear reasonable, False otherwise.
        """
        if not greeks:
            return False

        # Delta should be between -1 and 1
        if not (-1 <= greeks['delta'] <= 1):
            return False

        # Gamma should be positive and small
        if greeks['gamma'] < 0 or greeks['gamma'] > 1:
            return False

        # Vega should be positive
        if greeks['vega'] < 0:
            return False

        # Theoretical value should be positive
        if greeks['theoretical_value'] < 0:
            return False

        # Intrinsic should be non-negative
        if greeks['intrinsic_value'] < 0:
            return False

        # Extrinsic should be non-negative
        if greeks['extrinsic_value'] < 0:
            return False

        return True


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Example: AAPL call option
    # Stock: $175, Strike: $180, 30 days to expiration
    # Risk-free rate: 4.5%, Implied Volatility: 20%
    greeks = GreeksCalculator.calculate_greeks(
        S=175.00,        # Current stock price
        K=180.00,        # Strike price
        T=30/365.0,      # 30 days to expiration (in years)
        r=0.045,         # 4.5% risk-free rate
        sigma=0.20,      # 20% implied volatility
        option_type='call'
    )

    print("Example: AAPL $180 Call, 30 DTE")
    print(f"  Delta: {greeks['delta']} (hedge {abs(greeks['delta']*100):.0f} shares)")
    print(f"  Gamma: {greeks['gamma']}")
    print(f"  Theta: {greeks['theta']} (daily decay)")
    print(f"  Vega: {greeks['vega']} (per 1% IV change)")
    print(f"  Rho: {greeks['rho']}")
    print(f"  Price: ${greeks['theoretical_value']}")
    print(f"  Intrinsic: ${greeks['intrinsic_value']}")
    print(f"  Extrinsic: ${greeks['extrinsic_value']}")

    # Test IV rank
    iv_hist = [0.15, 0.16, 0.18, 0.20, 0.22, 0.25, 0.28, 0.30]
    iv_rank = GreeksCalculator.calculate_iv_rank(0.24, iv_hist)
    print(f"\nIV Rank: {iv_rank}% (current IV 0.24 vs history {iv_hist})")
