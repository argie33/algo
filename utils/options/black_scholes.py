"""Black-Scholes European option pricing and greeks.

Self-computed IV/delta for the options data POC (goal session 2026-09-12) - the free/
indicative data feeds we use (yfinance) supply raw quotes but not always reliable greeks,
so this fills that gap ourselves rather than requiring a paid data vendor.

Live-validated 2026-09-12 against MSFT: spot and option quotes must be time-aligned to the
same session close before pricing - comparing a live/after-hours stock tick against options
frozen at the prior 4pm close manufactures a fake negative time value on deep-ITM strikes
(options don't trade extended hours, the underlying does). Callers own that alignment; this
module assumes S and the option's quote are already from the same session.

Formulas: Hull, "Options, Futures, and Other Derivatives." Uses continuously-compounded
risk-free rate and no dividend yield adjustment (q=0) - callers pricing dividend-paying
underlyings over a period spanning an ex-date should supply a dividend-adjusted forward
price instead of raw spot, this module does not do that adjustment itself.
"""

import math
from statistics import NormalDist

_N = NormalDist()


def _d1_d2(
    spot: float, strike: float, time_to_expiry_years: float, risk_free_rate: float, iv: float
) -> tuple[float, float]:
    if spot <= 0 or strike <= 0:
        raise ValueError(f"spot and strike must be positive: spot={spot}, strike={strike}")
    if time_to_expiry_years <= 0:
        raise ValueError(f"time_to_expiry_years must be positive: {time_to_expiry_years}")
    if iv <= 0:
        raise ValueError(f"iv must be positive: {iv}")

    sqrt_t = math.sqrt(time_to_expiry_years)
    d1 = (math.log(spot / strike) + (risk_free_rate + 0.5 * iv**2) * time_to_expiry_years) / (iv * sqrt_t)
    d2 = d1 - iv * sqrt_t
    return d1, d2


def call_price(spot: float, strike: float, time_to_expiry_years: float, risk_free_rate: float, iv: float) -> float:
    """Black-Scholes theoretical price of a European call."""
    d1, d2 = _d1_d2(spot, strike, time_to_expiry_years, risk_free_rate, iv)
    return spot * _N.cdf(d1) - strike * math.exp(-risk_free_rate * time_to_expiry_years) * _N.cdf(d2)


def put_price(spot: float, strike: float, time_to_expiry_years: float, risk_free_rate: float, iv: float) -> float:
    """Black-Scholes theoretical price of a European put (via put-call parity)."""
    d1, d2 = _d1_d2(spot, strike, time_to_expiry_years, risk_free_rate, iv)
    return strike * math.exp(-risk_free_rate * time_to_expiry_years) * _N.cdf(-d2) - spot * _N.cdf(-d1)


def call_delta(spot: float, strike: float, time_to_expiry_years: float, risk_free_rate: float, iv: float) -> float:
    """Delta of a European call, in [0, 1]."""
    d1, _ = _d1_d2(spot, strike, time_to_expiry_years, risk_free_rate, iv)
    return _N.cdf(d1)


def put_delta(spot: float, strike: float, time_to_expiry_years: float, risk_free_rate: float, iv: float) -> float:
    """Delta of a European put, in [-1, 0]. Equals call_delta - 1 (put-call parity)."""
    return call_delta(spot, strike, time_to_expiry_years, risk_free_rate, iv) - 1.0


def implied_volatility(
    option_price: float,
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    risk_free_rate: float,
    is_call: bool,
    tolerance: float = 1e-6,
    max_iterations: int = 100,
) -> float:
    """Solve for IV via bisection given an observed option price.

    Bisection (not Newton-Raphson) because it can't diverge or overshoot into a negative/
    zero vega region - important for the free-tier feed's noisy penny-level ATM quotes,
    where a bad initial vega estimate can send Newton-Raphson off to nonsense values.

    Raises ValueError if option_price is not achievable at any positive IV (e.g. a quote
    below intrinsic value, or above the strike-bound max - both indicate a bad/stale quote,
    not a solvable pricing problem, so fail loudly rather than return a garbage IV).
    """
    if option_price <= 0:
        raise ValueError(f"option_price must be positive: {option_price}")

    price_fn = call_price if is_call else put_price

    lo, hi = 1e-4, 5.0  # 0.01% to 500% annualized vol - covers any real equity option
    price_lo = price_fn(spot, strike, time_to_expiry_years, risk_free_rate, lo)
    price_hi = price_fn(spot, strike, time_to_expiry_years, risk_free_rate, hi)

    if not (price_lo <= option_price <= price_hi):
        raise ValueError(
            f"option_price {option_price} not reachable for any IV in [{lo}, {hi}] "
            f"(bounds: [{price_lo:.4f}, {price_hi:.4f}]) - quote is likely below intrinsic "
            f"value or otherwise stale/bad, not a solvable implied-vol problem"
        )

    for _ in range(max_iterations):
        mid = (lo + hi) / 2
        price_mid = price_fn(spot, strike, time_to_expiry_years, risk_free_rate, mid)
        if abs(price_mid - option_price) < tolerance:
            return mid
        if price_mid < option_price:
            lo = mid
        else:
            hi = mid

    return (lo + hi) / 2
