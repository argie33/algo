#!/usr/bin/env python3
"""Regression tests for phase6_exit_execution.py's _retry_exit_trade and
_validate_exit_trade_response - continuing the 2026-08-24 test-coverage-completeness sweep.

Before writing these, verified _retry_exit_trade's retry-on-transient-error behavior is SAFE
(not a duplicate-order risk): executor.py's _send_alpaca_exit persists a stable client_order_id
in its own immediately-committed transaction before calling Alpaca, and only clears it on
confirmed success - a retry (from this function's own loop, or a full process crash/restart)
reuses the same id, and Alpaca's own client_order_id dedup prevents a genuinely separate
duplicate sell order. Retrying on TimeoutError/ConnectionError/OSError is deliberate and safe
by design, not a bug.
"""

from unittest.mock import MagicMock

import psycopg2
import pytest

from algo.orchestrator.phase6_exit_execution import _retry_exit_trade, _validate_exit_trade_response


class TestRetryExitTrade:
    def test_success_on_first_attempt_no_retry(self):
        executor = MagicMock()
        executor.exit_trade.return_value = {"success": True, "trade_id": 1, "message": "ok"}
        result = _retry_exit_trade(executor, trade_id=1)
        assert result == {"success": True, "trade_id": 1, "message": "ok"}
        assert executor.exit_trade.call_count == 1

    def test_retries_and_succeeds_on_transient_error(self, monkeypatch):
        monkeypatch.setattr("algo.orchestrator.phase6_exit_execution.time.sleep", lambda _s: None)
        executor = MagicMock()
        executor.exit_trade.side_effect = [
            TimeoutError("transient"),
            {"success": True, "trade_id": 1, "message": "ok"},
        ]
        result = _retry_exit_trade(executor, max_retries=3, trade_id=1)
        assert result["success"] is True
        assert executor.exit_trade.call_count == 2

    def test_exhausts_retries_and_raises(self, monkeypatch):
        monkeypatch.setattr("algo.orchestrator.phase6_exit_execution.time.sleep", lambda _s: None)
        executor = MagicMock()
        executor.exit_trade.side_effect = ConnectionError("still down")
        with pytest.raises(RuntimeError, match="Exit trade failed after retries"):
            _retry_exit_trade(executor, max_retries=2, trade_id=1)
        assert executor.exit_trade.call_count == 3  # initial + 2 retries

    def test_validation_error_returns_failure_dict_without_raising(self):
        """A ValueError/KeyError/AttributeError is NOT retried and does not propagate - it's
        converted to a clean failure result, distinct from the transient-error retry path."""
        executor = MagicMock()
        executor.exit_trade.side_effect = ValueError("bad price")
        result = _retry_exit_trade(executor, trade_id=1)
        assert result["success"] is False
        assert "bad price" in result["message"]
        assert executor.exit_trade.call_count == 1

    def test_database_error_raises_immediately_without_retry(self):
        """A DB error must not be retried (risk of a partially-executed trade being
        resubmitted against an uncertain DB state) - raises immediately instead."""
        executor = MagicMock()
        executor.exit_trade.side_effect = psycopg2.OperationalError("connection lost")
        with pytest.raises(RuntimeError, match="database error"):
            _retry_exit_trade(executor, max_retries=3, trade_id=1)
        assert executor.exit_trade.call_count == 1

    def test_unexpected_error_raises_immediately_without_retry(self):
        """An unrecognized exception type fails closed immediately (possible broker state
        divergence) rather than being silently retried."""
        executor = MagicMock()
        executor.exit_trade.side_effect = RuntimeError("something truly unexpected")
        with pytest.raises(RuntimeError, match="unexpectedly"):
            _retry_exit_trade(executor, max_retries=3, trade_id=1)
        assert executor.exit_trade.call_count == 1


class TestValidateExitTradeResponse:
    def test_valid_response_passes(self):
        _validate_exit_trade_response(
            {"success": True, "trade_id": 1, "message": "ok", "executed_price": 100.0, "filled_qty": 10},
            trade_id=1,
        )

    def test_non_dict_response_raises(self):
        with pytest.raises(RuntimeError, match="invalid type"):
            _validate_exit_trade_response("not a dict", trade_id=1)

    def test_missing_required_key_raises(self):
        with pytest.raises(RuntimeError, match="missing"):
            _validate_exit_trade_response({"success": True, "trade_id": 1}, trade_id=1)  # no "message"

    def test_success_missing_executed_price_warns_but_does_not_raise(self, caplog):
        _validate_exit_trade_response({"success": True, "trade_id": 1, "message": "ok", "filled_qty": 10}, trade_id=1)

    def test_success_missing_filled_qty_warns_but_does_not_raise(self, caplog):
        _validate_exit_trade_response(
            {"success": True, "trade_id": 1, "message": "ok", "executed_price": 100.0}, trade_id=1
        )

    def test_failed_response_does_not_require_execution_details(self):
        """A failed exit (success=False) legitimately has no executed_price/filled_qty -
        must not warn or raise about their absence."""
        _validate_exit_trade_response({"success": False, "trade_id": 1, "message": "rejected"}, trade_id=1)
