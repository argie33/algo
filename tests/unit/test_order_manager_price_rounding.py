#!/usr/bin/env python3
"""Regression tests for the 2026-07-21 order_manager.py Decimal-rounding fix.

send_bracket_order() used to round limit_price/stop_price with Python's built-in
round(x, 2) - binary-float representation makes this wrong at exact half-cent boundaries
(round(2.675, 2) == 2.67, not 2.68, because 2.675 isn't exactly representable in binary
float). Fixed to Decimal(str(x)).quantize(Decimal("0.01"), ROUND_HALF_UP), matching every
other price-rounding site in the codebase. This is the price actually submitted to the
broker - a real, live-money-consequential value, not a display figure.
"""

from unittest.mock import MagicMock, patch

from algo.trading.order_manager import OrderManager


def _mock_response(order_id="order-123"):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "id": order_id,
        "status": "accepted",
        "order_class": "bracket",
        "filled_avg_price": None,
        "legs": [],
    }
    return resp


class TestBracketOrderPriceRounding:
    def test_limit_price_rounds_correctly_at_half_cent_boundary(self):
        """round(2.675, 2) == 2.67 (wrong); Decimal ROUND_HALF_UP gives 2.68 (correct).
        This is the exact boundary case the bug produced silently-wrong broker orders on."""
        manager = OrderManager("fake_key", "fake_secret", "https://fake.alpaca.test")

        with (
            patch("algo.trading.order_manager.requests.post", return_value=_mock_response()) as mock_post,
            patch("algo.trading.order_manager.validator") as mock_validator,
        ):
            mock_validator.validate_order_response.return_value = {
                "valid": True,
                "status": "accepted",
                "filled_avg_price": None,
                "order_id": "order-123",
                "order_class": "bracket",
                "legs": [],
                "rejection_reason": None,
            }
            manager.send_bracket_order(
                symbol="TEST",
                shares=10,
                entry_price=2.675,
                stop_loss_price=2.5,
            )

        payload = mock_post.call_args.kwargs["json"]
        assert payload["limit_price"] == "2.68"

    def test_stop_price_rounds_correctly_at_half_cent_boundary(self):
        manager = OrderManager("fake_key", "fake_secret", "https://fake.alpaca.test")

        with (
            patch("algo.trading.order_manager.requests.post", return_value=_mock_response()) as mock_post,
            patch("algo.trading.order_manager.validator") as mock_validator,
        ):
            mock_validator.validate_order_response.return_value = {
                "valid": True,
                "status": "accepted",
                "filled_avg_price": None,
                "order_id": "order-123",
                "order_class": "bracket",
                "legs": [],
                "rejection_reason": None,
            }
            manager.send_bracket_order(
                symbol="TEST",
                shares=10,
                entry_price=10.0,
                stop_loss_price=9.005,
            )

        payload = mock_post.call_args.kwargs["json"]
        # round(9.005, 2) == 9.0 (wrong, drops precision); Decimal ROUND_HALF_UP gives 9.01
        assert payload["stop_loss"]["stop_price"] == "9.01"

    def test_take_profit_fallback_uses_decimal_not_float_roundtrip(self):
        """The take_profit fallback (1.5R from entry) must not convert its Decimal result
        to float and back through round() - that reintroduces the same binary-float risk
        the Decimal quantize was meant to avoid."""
        manager = OrderManager("fake_key", "fake_secret", "https://fake.alpaca.test")

        with (
            patch("algo.trading.order_manager.requests.post", return_value=_mock_response()) as mock_post,
            patch("algo.trading.order_manager.validator") as mock_validator,
        ):
            mock_validator.validate_order_response.return_value = {
                "valid": True,
                "status": "accepted",
                "filled_avg_price": None,
                "order_id": "order-123",
                "order_class": "bracket",
                "legs": [],
                "rejection_reason": None,
            }
            # entry=10.005, stop=10.0 -> risk=0.005 -> tp = 10.005 + 1.5*0.005 = 10.0125
            manager.send_bracket_order(
                symbol="TEST",
                shares=10,
                entry_price=10.005,
                stop_loss_price=10.0,
                take_profit_price=None,
            )

        payload = mock_post.call_args.kwargs["json"]
        # Decimal ROUND_HALF_UP: 10.0125 -> 10.01 (round-half-up rounds .5 away from zero
        # at the 3rd decimal, but quantize to 2 places looks only at the 3rd digit "2" < 5)
        # Confirm it's a clean 2-decimal string, not a float-roundtrip artifact.
        tp_price = payload["take_profit"]["limit_price"]
        assert tp_price == "10.01"
        assert len(tp_price.split(".")[1]) == 2  # exactly 2 decimal places, no float noise


class TestSendBracketOrderToleratesNoneStopLoss:
    """Regression test for the 2026-07-27 fix: send_bracket_order()'s own docstring promises
    it "Falls back to simple limit order if bracket can't be sent (no stop)", and the function
    body has real handling for stop_loss_price=None (the `if stop_loss_price is not None and
    stop_loss_price > 0:` branch a few lines down) - but the very first log statement
    unconditionally formatted stop_loss_price with `:.2f}`, which raises TypeError on None
    before that graceful handling is ever reached. Only production caller (executor.py) always
    passes a float today, so this was latent rather than live, but it defeats the function's
    own documented no-stop fallback contract."""

    def test_none_stop_loss_does_not_crash_before_reaching_fallback_logic(self):
        manager = OrderManager("fake_key", "fake_secret", "https://fake.alpaca.test")

        with (
            patch("algo.trading.order_manager.requests.post", return_value=_mock_response()) as mock_post,
            patch("algo.trading.order_manager.validator") as mock_validator,
        ):
            mock_validator.validate_order_response.return_value = {
                "valid": True,
                "status": "accepted",
                "filled_avg_price": None,
                "order_id": "order-123",
                "order_class": "bracket",
                "legs": [],
                "rejection_reason": None,
            }
            result = manager.send_bracket_order(
                symbol="TEST",
                shares=10,
                entry_price=10.0,
                stop_loss_price=None,
            )

        # FAIL-FAST: Stop loss protection is non-negotiable. System must reject orders without valid stop-loss.
        # Allowing None stop_loss would create naked positions (no stop-loss protection), violating risk governance.
        assert result["success"] is False
        assert "stop_loss_price" in result["message"].lower()
        # Order should NOT be sent to Alpaca when stop_loss validation fails
        mock_post.assert_not_called()


class TestClientOrderIdIdempotency:
    """Regression tests for the 2026-07-26 fix: send_bracket_order() previously sent no
    client_order_id to Alpaca at all, so a submission whose HTTP response is lost to a
    timeout (order may have actually reached Alpaca and been accepted) had no broker-side
    protection against a later retry placing a genuine duplicate order - our own
    duplicate-position check only queries algo_trades/algo_positions, which never gets a
    row written when we never received a response to check against. Fixed by passing a
    deterministic idempotency_key (not the random per-attempt trade_id) as client_order_id,
    so Alpaca rejects a resubmission of the same underlying trade intent as a duplicate."""

    def test_client_order_id_included_when_provided(self):
        manager = OrderManager("fake_key", "fake_secret", "https://fake.alpaca.test")

        with (
            patch("algo.trading.order_manager.requests.post", return_value=_mock_response()) as mock_post,
            patch("algo.trading.order_manager.validator") as mock_validator,
        ):
            mock_validator.validate_order_response.return_value = {
                "valid": True,
                "status": "accepted",
                "filled_avg_price": None,
                "order_id": "order-123",
                "order_class": "bracket",
                "legs": [],
                "rejection_reason": None,
            }
            manager.send_bracket_order(
                symbol="TEST",
                shares=10,
                entry_price=10.0,
                stop_loss_price=9.0,
                client_order_id="deadbeef" * 6,
            )

        payload = mock_post.call_args.kwargs["json"]
        assert payload["client_order_id"] == "deadbeef" * 6

    def test_client_order_id_omitted_when_not_provided(self):
        """Backward compatible: existing callers that don't pass client_order_id must not
        send a null/empty field to Alpaca's API."""
        manager = OrderManager("fake_key", "fake_secret", "https://fake.alpaca.test")

        with (
            patch("algo.trading.order_manager.requests.post", return_value=_mock_response()) as mock_post,
            patch("algo.trading.order_manager.validator") as mock_validator,
        ):
            mock_validator.validate_order_response.return_value = {
                "valid": True,
                "status": "accepted",
                "filled_avg_price": None,
                "order_id": "order-123",
                "order_class": "bracket",
                "legs": [],
                "rejection_reason": None,
            }
            manager.send_bracket_order(
                symbol="TEST",
                shares=10,
                entry_price=10.0,
                stop_loss_price=9.0,
            )

        payload = mock_post.call_args.kwargs["json"]
        assert "client_order_id" not in payload

    def test_executor_passes_idempotency_key_not_trade_id(self):
        """The value threaded into client_order_id must be the deterministic idempotency_key
        computed from (symbol, signal_date, entry_price, stop_loss_price), not the random
        per-attempt trade_id - otherwise every retry gets a different client_order_id and
        Alpaca can never recognize it as a duplicate."""
        from algo.trading.executor import TradeExecutor

        executor = MagicMock(spec=TradeExecutor)
        executor.alpaca_base_url = "https://fake.alpaca.test"
        executor.order_manager = MagicMock()
        executor.order_manager.send_bracket_order.return_value = {
            "success": True,
            "order_id": "order-123",
            "status": "accepted",
            "executed_price": 10.0,
        }

        TradeExecutor._submit_and_validate_order(
            executor,
            symbol="TEST",
            trade_id="TRD-RANDOMUUID1",
            shares=10,
            entry_price=10.0,
            stop_loss_price=9.0,
            target_1_price=None,
            execution_mode="auto",
            idempotency_key="stable-idempotency-hash",
        )

        call_kwargs = executor.order_manager.send_bracket_order.call_args.kwargs
        assert call_kwargs["client_order_id"] == "stable-idempotency-hash"
        assert call_kwargs["client_order_id"] != "TRD-RANDOMUUID1"
