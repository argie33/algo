"""Regression test for a NaN-comparison-guard gap in lambda/api/models/requests.py, found
2026-08-10 while auditing HTTP-reachable surfaces for the same bug class already fixed 11x
this session in internal money-math call sites (`value <= 0` never catches NaN - NaN
comparisons are always False in Python).

PositionUpdateRequest.validate_stop_loss_price/validate_target_price/validate_entry_price,
TradePreviewRequest.validate_stop_loss, and ManualTradeRequest.validate_stop_loss all used
bare `v <= 0` / `v >= entry_price` checks with no isnan/isinf guard. A NaN stop_loss_price
sent to POST /api/position/update would sail through every validator (including the
cross-field `risk_amount < 0.01` check) and get written straight into algo_positions for a
real open position - which the exit engine then reads for the position's remaining
lifetime. POST /api/trades/manual (ManualTradeRequest) has the identical gap for a
brand-new manually-logged real trade entry.

'lambda' is a Python keyword, so lambda/api modules are loaded via importlib; importing
lambda.api.routes.positions first puts lambda/api on sys.path so `models.requests` becomes
directly importable (matches test_position_update_entry_price_validation.py's approach).
"""

import importlib
import math

import pytest
from pydantic import ValidationError

importlib.import_module("lambda.api.routes.positions")
from models.requests import ManualTradeRequest, PositionUpdateRequest, TradePreviewRequest


class TestPositionUpdateRequestRejectsNaN:
    def test_nan_stop_loss_price_rejected(self):
        with pytest.raises(ValidationError):
            PositionUpdateRequest(position_id=1, stop_loss_price=float("nan"))

    def test_infinite_stop_loss_price_rejected(self):
        with pytest.raises(ValidationError):
            PositionUpdateRequest(position_id=1, stop_loss_price=float("inf"))

    def test_nan_target_price_rejected(self):
        with pytest.raises(ValidationError):
            PositionUpdateRequest(position_id=1, target_1_price=float("nan"))

    def test_nan_entry_price_rejected(self):
        with pytest.raises(ValidationError):
            PositionUpdateRequest(position_id=1, entry_price=float("nan"))

    def test_normal_stop_loss_price_still_accepted(self):
        req = PositionUpdateRequest(position_id=1, stop_loss_price=95.0)
        assert req.stop_loss_price == 95.0


class TestTradePreviewRequestRejectsNaN:
    def test_nan_stop_loss_price_rejected(self):
        with pytest.raises(ValidationError):
            TradePreviewRequest(symbol="AAPL", entry_price=100.0, stop_loss_price=float("nan"))

    def test_normal_stop_loss_price_still_accepted(self):
        req = TradePreviewRequest(symbol="AAPL", entry_price=100.0, stop_loss_price=95.0)
        assert req.stop_loss_price == 95.0


class TestManualTradeRequestRejectsNaN:
    def test_nan_stop_loss_price_rejected(self):
        with pytest.raises(ValidationError):
            ManualTradeRequest(symbol="AAPL", quantity=10, price=100.0, stop_loss_price=float("nan"))

    def test_infinite_stop_loss_price_rejected(self):
        with pytest.raises(ValidationError):
            ManualTradeRequest(symbol="AAPL", quantity=10, price=100.0, stop_loss_price=float("inf"))

    def test_normal_stop_loss_price_still_accepted(self):
        req = ManualTradeRequest(symbol="AAPL", quantity=10, price=100.0, stop_loss_price=95.0)
        assert req.stop_loss_price == 95.0


def test_confirm_fixed_source_uses_isnan_guard():
    """Sanity check tying this test back to the real guard pattern, so it can't drift."""
    import inspect

    from models import requests as requests_module

    source = inspect.getsource(requests_module)
    assert source.count("math.isnan") >= 4, "expected an isnan guard in each of the 4 fixed validators"
    assert "math.isinf" in source
