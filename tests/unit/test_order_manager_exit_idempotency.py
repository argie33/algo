#!/usr/bin/env python3
"""Regression test: send_market_exit() must carry a broker-side idempotency key on retry.

Unlike send_bracket_order() (entries), send_market_exit() had no client_order_id at all.
Its retry loop catches requests.RequestException/Timeout and resubmits - if attempt 1's
response was lost to a timeout but the order actually reached Alpaca (ambiguous outcome,
not a rejection), attempt 2 submitted a genuinely separate market sell order for the same
position: a real double-sell, not a harmless duplicate no-op. Fixed by threading a
client_order_id (generated once per call in executor.py's _send_alpaca_exit, stable across
this call's own retry attempts) through to every POST /v2/orders payload.
"""

from unittest.mock import MagicMock, patch

import requests

from algo.trading.order_manager import OrderManager


def _mock_response(status_code=200, order_id="exit-order-1", filled_avg_price=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {
        "id": order_id,
        "status": "new",
        "filled_avg_price": filled_avg_price,
    }
    return resp


class TestSendMarketExitIdempotency:
    def test_client_order_id_included_when_provided(self):
        manager = OrderManager("fake_key", "fake_secret", "https://fake.alpaca.test")

        with patch("algo.trading.order_manager.requests.post", return_value=_mock_response()) as mock_post:
            manager.send_market_exit("TEST", 10, execution_mode="auto", client_order_id="exit-abc123")

        payload = mock_post.call_args.kwargs["json"]
        assert payload["client_order_id"] == "exit-abc123"

    def test_same_client_order_id_reused_across_retry_attempts(self):
        """The exact bug: a timeout on attempt 1 (order may have reached Alpaca) must not
        cause attempt 2 to submit under a different identity - Alpaca can only dedupe
        retries that share the same client_order_id."""
        manager = OrderManager("fake_key", "fake_secret", "https://fake.alpaca.test")

        with patch(
            "algo.trading.order_manager.requests.post",
            side_effect=[requests.Timeout("timed out"), _mock_response()],
        ) as mock_post, patch("algo.trading.order_manager.time.sleep"):
            result = manager.send_market_exit("TEST", 10, execution_mode="auto", client_order_id="exit-stable-1")

        assert result["success"] is True
        assert mock_post.call_count == 2
        first_payload = mock_post.call_args_list[0].kwargs["json"]
        second_payload = mock_post.call_args_list[1].kwargs["json"]
        assert first_payload["client_order_id"] == "exit-stable-1"
        assert second_payload["client_order_id"] == "exit-stable-1"

    def test_no_client_order_id_key_when_not_provided(self):
        """Paper/test callers that don't pass one must not send a bogus/empty field."""
        manager = OrderManager("fake_key", "fake_secret", "https://fake.alpaca.test")

        with patch("algo.trading.order_manager.requests.post", return_value=_mock_response()) as mock_post:
            manager.send_market_exit("TEST", 10, execution_mode="auto")

        payload = mock_post.call_args.kwargs["json"]
        assert "client_order_id" not in payload


class TestExecutorGeneratesFreshIdPerCall:
    def test_send_alpaca_exit_passes_a_client_order_id(self):
        from algo.trading.executor import TradeExecutor

        mock_order_manager = MagicMock()
        mock_order_manager.send_market_exit.return_value = {"success": True, "order_id": "x", "filled_price": 1.0}

        executor = object.__new__(TradeExecutor)
        executor.order_manager = mock_order_manager
        executor.execution_mode = "auto"

        executor._send_alpaca_exit("TEST", 5)

        call_kwargs = mock_order_manager.send_market_exit.call_args
        args, kwargs = call_kwargs
        passed_id = kwargs.get("client_order_id") if "client_order_id" in kwargs else (args[3] if len(args) > 3 else None)
        assert passed_id, "executor must pass a non-empty client_order_id to send_market_exit"

    def test_two_separate_calls_get_different_ids(self):
        """Two distinct exit calls (e.g. two different trades, or the same trade on two
        different days) must NOT share an id - that would make Alpaca reject the second,
        legitimate exit as a duplicate of the first."""
        from algo.trading.executor import TradeExecutor

        mock_order_manager = MagicMock()
        mock_order_manager.send_market_exit.return_value = {"success": True, "order_id": "x", "filled_price": 1.0}

        executor = object.__new__(TradeExecutor)
        executor.order_manager = mock_order_manager
        executor.execution_mode = "auto"

        executor._send_alpaca_exit("TEST", 5)
        executor._send_alpaca_exit("TEST", 5)

        id_1 = mock_order_manager.send_market_exit.call_args_list[0].args[3]
        id_2 = mock_order_manager.send_market_exit.call_args_list[1].args[3]
        assert id_1 != id_2
