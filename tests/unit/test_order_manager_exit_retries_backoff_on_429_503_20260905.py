"""Regression test: OrderManager.send_market_exit's 429/503 branch fell straight through to
the next loop iteration with NO backoff sleep at all - unlike send_bracket_order,
cancel_bracket_orders, replace_order_stop_price, and submit_standalone_protective_stop, which
all sleep 2**attempt seconds on a transient 429/503 before retrying. Found 2026-09-05
(real-money-readiness order-execution audit): a rate-limited/unavailable response on an EXIT
order - the one order-critical call most likely to already be rate-limited (e.g. a
circuit-breaker-triggered mass exit hitting the API repeatedly in a short window) - busy-looped
3 attempts back-to-back instead of backing off like every other retry loop in this file.

Fixed by adding the same `if status_code in (429, 503) and attempt < max_attempts - 1:
time.sleep(2**attempt); continue` branch used everywhere else.
"""

from unittest.mock import MagicMock, patch

from algo.trading.order_manager import OrderManager


def _make_manager():
    return OrderManager("key", "secret", "https://paper-api.alpaca.markets")


def _filled_response():
    resp = MagicMock(status_code=200)
    resp.json.return_value = {
        "id": "exit-order-789",
        "status": "filled",
        "filled_avg_price": "50.25",
        "filled_qty": "10",
    }
    return resp


class TestExitRetriesBackoffOn429503:
    def test_429_then_success_sleeps_before_retrying(self):
        manager = _make_manager()
        rate_limited = MagicMock(status_code=429, text="rate limited")

        with (
            patch(
                "algo.trading.order_manager.requests.post",
                side_effect=[rate_limited, _filled_response()],
            ),
            patch("algo.trading.order_manager.time.sleep") as mock_sleep,
        ):
            result = manager.send_market_exit("MSFT", 10, execution_mode="auto")

        assert result["success"] is True
        mock_sleep.assert_called_once_with(1)  # 2**0

    def test_503_exhausts_retries_with_backoff_between_each_attempt(self):
        manager = _make_manager()
        unavailable = MagicMock(status_code=503, text="service unavailable")

        with (
            patch("algo.trading.order_manager.requests.post", return_value=unavailable) as mock_post,
            patch("algo.trading.order_manager.time.sleep") as mock_sleep,
        ):
            result = manager.send_market_exit("MSFT", 10, execution_mode="auto")

        assert result["success"] is False
        assert mock_post.call_count == 3
        # Backoff must be called between attempts (not zero-delay busy-looping) - exactly
        # 2 sleeps for 3 attempts, with increasing (or at least non-zero) wait times.
        assert mock_sleep.call_count == 2
        sleep_args = [call.args[0] for call in mock_sleep.call_args_list]
        assert all(arg > 0 for arg in sleep_args)
