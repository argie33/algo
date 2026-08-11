#!/usr/bin/env python3
"""Regression test: PositionSizer._calculate_with_external_cursor's safety validations
(portfolio value > 0, stop < entry, non-empty symbol, etc) must raise ValueError - not a
bare `assert` - so calculate_position_size()'s own except clause can wrap them into the
RuntimeError its docstring promises ("Raises RuntimeError/ValueError for all error
conditions"), and so Phase 8's per-symbol exception handlers (which catch
ValueError/RuntimeError/TypeError/AttributeError, not AssertionError) actually catch them.

Found via adversarial stress-testing: a raw AssertionError from a bad-data symbol would
propagate past every layer of exception handling in phase8_entry_execution.py, aborting
entry execution for every remaining symbol in that run's batch instead of cleanly skipping
just the one bad-data symbol. Bare `assert` is also silently stripped entirely under
`python -O`/`PYTHONOPTIMIZE=1`, which would let the single most basic long-only
risk-management invariant (stop < entry) through with zero validation.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from algo.trading.position_sizer import PositionSizer

CONFIG = {
    "base_risk_pct": 1.0,
    "max_positions": 15,
    "min_risk_pct_floor": 0.5,
    "max_position_size_pct": 10.0,
    "max_concentration_pct": 15.0,
    "max_total_invested_pct": 90.0,
    "max_total_risk_pct": 4.0,
    "risk_reduction_at_minus_5": 0.75,
    "risk_reduction_at_minus_10": 0.5,
    "risk_reduction_at_minus_15": 0.25,
    "risk_reduction_at_minus_20": 0.0,
    "vix_caution_threshold": 25.0,
    "vix_max_threshold": 35.0,
    "vix_caution_risk_reduction": 0.5,
}


def _make_sizer():
    return PositionSizer(config=dict(CONFIG))


def _patched(sizer):
    return (
        patch.object(sizer, "get_position_count", return_value=1),
        patch.object(sizer, "get_active_positions_value", return_value=Decimal("10000")),
        patch.object(sizer, "get_risk_adjustment", return_value=Decimal("1.0")),
        patch.object(sizer, "get_market_exposure_multiplier", return_value=Decimal("1.0")),
        patch.object(sizer, "get_phase_size_multiplier", return_value=1.0),
        patch.object(sizer, "get_vix_caution_multiplier", return_value=Decimal("1.0")),
        patch.object(sizer, "get_position_size_multiplier_from_regime", return_value=1.0),
    )


def _call(sizer, **kwargs):
    defaults = {
        "symbol": "AAPL",
        "entry_price": Decimal("100"),
        "stop_loss_price": Decimal("90"),
        "portfolio_value": Decimal("100000"),
        "enforce_total_risk_limit": False,
    }
    defaults.update(kwargs)
    patches = _patched(sizer)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
        return sizer.calculate_position_size(**defaults)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"portfolio_value": Decimal("0")},
        {"portfolio_value": Decimal("-100")},
        {"entry_price": Decimal("90"), "stop_loss_price": Decimal("100")},  # stop >= entry
        {"entry_price": Decimal("100"), "stop_loss_price": Decimal("100")},  # stop == entry
        {"entry_price": Decimal("0")},
        {"entry_price": Decimal("-5")},
        {"stop_loss_price": Decimal("0")},
        {"symbol": ""},
    ],
)
def test_invalid_inputs_raise_runtime_error_not_assertion_error(kwargs):
    sizer = _make_sizer()
    with pytest.raises(RuntimeError) as exc_info:
        _call(sizer, **kwargs)
    # Must be the documented RuntimeError wrapping, never a raw AssertionError leaking through -
    # pytest.raises(RuntimeError) would already fail an AssertionError doesn't subclass it, but
    # assert explicitly too so a future refactor can't silently reintroduce bare `assert`.
    assert not isinstance(exc_info.value, AssertionError)
