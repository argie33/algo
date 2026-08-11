#!/usr/bin/env python3
"""Regression test for two bugs found by fuzzing PositionSizer.calculate_position_size()
with pathological inputs on 2026-08-10 (all real Phase 8 call sites always pass float, so
neither was reachable in current production paths - but calculate_position_size's own
signature is `entry_price: Any, stop_loss_price: Any`, and its internal
`Decimal(str(entry_price))` normalization pattern both imply broader input types are a
supported contract, not just float).

Bug 1: `if entry_price <= 0 or stop_loss_price >= entry_price:` (a redundant second guard,
already covered by the entry_dec/stop_dec ValueError checks above it) compared the RAW
Any-typed parameters directly against int 0, instead of the already-validated Decimals.
A string entry_price/stop_loss_price crashed with an uncaught
"TypeError: '<=' not supported between instances of 'str' and 'int'" for ANY string input -
including a perfectly valid one like ("100.00", "95.00") - instead of either succeeding or
returning the clean {"status": "invalid", ...} result this branch exists to produce.
A second instance of the same class: the final success return's
f"... ${entry_price:.2f} ..." applied a numeric format spec to the same raw string,
crashing with "ValueError: Unknown format code 'f' for object of type 'str'".

Bug 2: decimal.InvalidOperation (raised by e.g. `Decimal("nan") > 0` - ordering comparisons
with a NaN Decimal are invalid, unlike float NaN which just returns False) is an
ArithmeticError, not a ValueError/ZeroDivisionError/TypeError - it fell through
calculate_position_size's except clauses uncaught, breaking this function's own documented
contract ("Raises RuntimeError/ValueError for all error conditions").
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


class TestStringTypedPriceInputs:
    def test_valid_string_prices_succeed_not_typeerror(self):
        """A valid string entry_price/stop_loss_price must size normally, not crash with
        "'<=' not supported between instances of 'str' and 'int'"."""
        sizer = _make_sizer()
        result = _call(sizer, entry_price="100.00", stop_loss_price="95.00")
        assert result["status"] == "ok"
        assert result["shares"] > 0

    def test_invalid_string_prices_raise_clean_runtime_error(self):
        """stop >= entry as strings must raise the documented RuntimeError, not TypeError."""
        sizer = _make_sizer()
        with pytest.raises(RuntimeError) as exc_info:
            _call(sizer, entry_price="100.00", stop_loss_price="105.00")
        assert not isinstance(exc_info.value, TypeError)


class TestNanPriceInputs:
    def test_nan_entry_price_raises_runtime_error_not_bare_invalid_operation(self):
        sizer = _make_sizer()
        with pytest.raises(RuntimeError) as exc_info:
            _call(sizer, entry_price=Decimal("nan"))
        # Must be wrapped, not a raw decimal.InvalidOperation leaking past both except clauses.
        assert "InvalidOperation" not in type(exc_info.value).__name__

    def test_nan_stop_price_raises_runtime_error_not_bare_invalid_operation(self):
        sizer = _make_sizer()
        with pytest.raises(RuntimeError) as exc_info:
            _call(sizer, stop_loss_price=Decimal("nan"))
        assert "InvalidOperation" not in type(exc_info.value).__name__
