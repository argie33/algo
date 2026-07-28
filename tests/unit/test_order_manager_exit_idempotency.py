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


class TestExecutorPersistsPendingClientOrderId:
    """Regression coverage for the crash-safe exit idempotency fix (migration 1166):
    _send_alpaca_exit must persist its client_order_id to algo_trades.
    pending_exit_client_order_id in its own committed transaction *before* calling
    Alpaca, and reuse an existing pending value instead of minting a new one - so a
    crash-recovery retry submits under the same id Alpaca already saw, instead of a
    genuinely new duplicate order.
    """

    def _mock_no_existing_pending(self, executor):
        """Simulate _with_cursor's DatabaseContext round-trip with no prior pending row."""
        cur = MagicMock()
        cur.fetchone.return_value = None
        executor._with_cursor = MagicMock(side_effect=lambda fn, acquire_locks=False: fn(cur))
        return cur

    def test_send_alpaca_exit_passes_a_client_order_id(self):
        from algo.trading.executor import TradeExecutor

        mock_order_manager = MagicMock()
        mock_order_manager.send_market_exit.return_value = {"success": True, "order_id": "x", "filled_price": 1.0}

        executor = object.__new__(TradeExecutor)
        executor.order_manager = mock_order_manager
        executor.execution_mode = "auto"
        self._mock_no_existing_pending(executor)

        executor._send_alpaca_exit("TEST", 5, trade_id=42)

        call_kwargs = mock_order_manager.send_market_exit.call_args
        args, kwargs = call_kwargs
        passed_id = kwargs.get("client_order_id") if "client_order_id" in kwargs else (args[3] if len(args) > 3 else None)
        assert passed_id, "executor must pass a non-empty client_order_id to send_market_exit"

    def test_two_different_trades_get_different_ids(self):
        """Two distinct exits for two different trades must NOT share an id - that would
        make Alpaca reject the second, legitimate exit as a duplicate of the first."""
        from algo.trading.executor import TradeExecutor

        mock_order_manager = MagicMock()
        mock_order_manager.send_market_exit.return_value = {"success": True, "order_id": "x", "filled_price": 1.0}

        executor = object.__new__(TradeExecutor)
        executor.order_manager = mock_order_manager
        executor.execution_mode = "auto"
        self._mock_no_existing_pending(executor)

        executor._send_alpaca_exit("TEST", 5, trade_id=42)
        executor._send_alpaca_exit("TEST", 5, trade_id=43)

        id_1 = mock_order_manager.send_market_exit.call_args_list[0].args[3]
        id_2 = mock_order_manager.send_market_exit.call_args_list[1].args[3]
        assert id_1 != id_2
        # Check the trade_id as a delimited token (exit-{trade_id}-{hex}), not raw substring
        # containment - the random hex suffix can coincidentally contain the other trade_id's
        # digits (e.g. "...439c" contains "43"), making a substring check flaky.
        assert id_1.startswith("exit-42-")
        assert id_2.startswith("exit-43-")

    def test_crash_recovery_reuses_existing_pending_client_order_id(self):
        """The actual bug fix: if algo_trades.pending_exit_client_order_id is already set
        for this trade (a prior attempt crashed between Alpaca confirming the fill and the
        exit transaction committing), the retry must reuse that exact value - not mint a
        fresh one - so Alpaca's own idempotency dedupes the resubmission."""
        from algo.trading.executor import TradeExecutor

        mock_order_manager = MagicMock()
        mock_order_manager.send_market_exit.return_value = {"success": True, "order_id": "x", "filled_price": 1.0}

        executor = object.__new__(TradeExecutor)
        executor.order_manager = mock_order_manager
        executor.execution_mode = "auto"

        cur = MagicMock()
        cur.fetchone.return_value = ("exit-42-alreadypending",)
        executor._with_cursor = MagicMock(side_effect=lambda fn, acquire_locks=False: fn(cur))

        executor._send_alpaca_exit("TEST", 5, trade_id=42)

        passed_id = mock_order_manager.send_market_exit.call_args.args[3]
        assert passed_id == "exit-42-alreadypending"
        # Must not attempt to overwrite an existing pending id with a fresh one.
        update_calls = [c for c in cur.execute.call_args_list if "UPDATE algo_trades" in c.args[0]]
        assert not update_calls, "must not mint/persist a new id when one is already pending"
