"""Round-trip and sanity checks for utils/options/black_scholes.py.

Live-validated separately against real MSFT quotes (goal session 2026-09-12); these are the
offline unit checks: price/IV round-trip consistency, delta bounds, and the failure mode for
unreachable (bad/stale) quotes.
"""

import math

import pytest

from utils.options.black_scholes import (
    call_delta,
    call_price,
    implied_volatility,
    put_delta,
    put_price,
)


def test_call_price_iv_round_trip():
    spot, strike, t, r, iv = 100.0, 95.0, 30 / 365, 0.045, 0.25
    price = call_price(spot, strike, t, r, iv)
    recovered_iv = implied_volatility(price, spot, strike, t, r, is_call=True)
    assert recovered_iv == pytest.approx(iv, abs=1e-4)


def test_put_price_iv_round_trip():
    spot, strike, t, r, iv = 100.0, 105.0, 45 / 365, 0.045, 0.30
    price = put_price(spot, strike, t, r, iv)
    recovered_iv = implied_volatility(price, spot, strike, t, r, is_call=False)
    assert recovered_iv == pytest.approx(iv, abs=1e-4)


def test_call_delta_bounds_and_monotonicity():
    spot, t, r, iv = 100.0, 30 / 365, 0.045, 0.25
    deep_itm = call_delta(spot, 50.0, t, r, iv)
    atm = call_delta(spot, 100.0, t, r, iv)
    deep_otm = call_delta(spot, 200.0, t, r, iv)
    assert 0.0 <= deep_otm < atm < deep_itm <= 1.0


def test_put_delta_bounds_and_parity_relationship():
    spot, strike, t, r, iv = 100.0, 90.0, 30 / 365, 0.045, 0.25
    cd = call_delta(spot, strike, t, r, iv)
    pd = put_delta(spot, strike, t, r, iv)
    assert -1.0 <= pd <= 0.0
    assert pd == pytest.approx(cd - 1.0)


def test_csp_target_delta_zone_is_otm_puts_near_015_030():
    # 0.15-0.30 delta zone for CSPs: strikes below spot, not adjacent-to-spot puts
    spot, t, r, iv = 100.0, 30 / 365, 0.045, 0.25
    near_money_delta = abs(put_delta(spot, 98.0, t, r, iv))
    far_otm_delta = abs(put_delta(spot, 85.0, t, r, iv))
    assert far_otm_delta < near_money_delta


def test_implied_volatility_raises_on_unreachable_price():
    # A price below intrinsic value (deep ITM, priced at less than spot-strike) is not a
    # solvable IV problem - this is the exact "stray after-hours tick vs stale option quote"
    # failure mode found live 2026-09-12, must fail loudly rather than return garbage.
    spot, strike, t, r = 100.0, 50.0, 30 / 365, 0.045
    bad_price = 1.0  # intrinsic alone is ~50, so this is far below reachable range
    with pytest.raises(ValueError, match="not reachable"):
        implied_volatility(bad_price, spot, strike, t, r, is_call=True)


def test_zero_or_negative_iv_rejected():
    from utils.options.black_scholes import call_price

    with pytest.raises(ValueError):
        call_price(100.0, 95.0, 0.1, 0.045, 0.0)


def test_zero_time_to_expiry_rejected():
    from utils.options.black_scholes import call_price

    with pytest.raises(ValueError):
        call_price(100.0, 95.0, 0.0, 0.045, 0.25)


def test_price_is_finite_and_positive_for_reasonable_inputs():
    price = call_price(100.0, 100.0, 30 / 365, 0.045, 0.20)
    assert math.isfinite(price)
    assert price > 0
