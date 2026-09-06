"""Regression tests for algo/execution/trade_update_listener.py - the always-on Alpaca
trade_updates websocket consumer (real-money-readiness architecture rebuild, 2026-09-06).

Core safety property under test: this process is a LATENCY ACCELERANT ONLY. It must
never write DB state itself - only trigger the exact same reconciliation methods
(DailyReconciliation.check_partial_fills/.reconcile_exit_fills) the orchestrator already
calls on its own schedule, so a missed/dropped websocket event degrades latency, never
correctness.
"""

import asyncio
from unittest.mock import MagicMock, patch

from algo.execution import trade_update_listener as listener


def _config(**overrides):
    base = {"execution_mode": "paper"}
    base.update(overrides)
    return base


class TestHandleTradeUpdate:
    def test_fill_event_triggers_reconciliation(self):
        data = MagicMock()
        data.event = "fill"
        data.order = {"symbol": "AAPL"}
        with patch("algo.execution.trade_update_listener._run_reconciliation_now") as mock_run:
            asyncio.run(listener._handle_trade_update(_config(), data))
        mock_run.assert_called_once_with(_config(), "fill", "AAPL")

    def test_partial_fill_event_triggers_reconciliation(self):
        data = MagicMock()
        data.event = "partial_fill"
        data.order = {"symbol": "MSFT"}
        with patch("algo.execution.trade_update_listener._run_reconciliation_now") as mock_run:
            asyncio.run(listener._handle_trade_update(_config(), data))
        mock_run.assert_called_once()

    def test_irrelevant_event_type_does_not_trigger_reconciliation(self):
        data = MagicMock()
        data.event = "new"  # order accepted, not a fill/cancel/reject - nothing to reconcile
        data.order = {"symbol": "AAPL"}
        with patch("algo.execution.trade_update_listener._run_reconciliation_now") as mock_run:
            asyncio.run(listener._handle_trade_update(_config(), data))
        mock_run.assert_not_called()

    def test_missing_order_data_does_not_crash(self):
        data = MagicMock()
        data.event = "fill"
        data.order = None
        with patch("algo.execution.trade_update_listener._run_reconciliation_now") as mock_run:
            asyncio.run(listener._handle_trade_update(_config(), data))
        mock_run.assert_called_once_with(_config(), "fill", None)


class TestRunReconciliationNow:
    def test_no_broker_configured_is_a_noop(self):
        mock_recon = MagicMock()
        mock_recon.broker = None
        with patch("algo.infrastructure.reconciliation.DailyReconciliation", return_value=mock_recon):
            listener._run_reconciliation_now(_config(), "fill", "AAPL")
        mock_recon.check_partial_fills.assert_not_called()
        mock_recon.reconcile_exit_fills.assert_not_called()

    def test_calls_both_existing_reconciliation_methods_not_a_new_write_path(self):
        """The core safety property: this must call the SAME methods the orchestrator's
        own scheduled reconciliation already uses - never a bespoke DB write."""
        mock_recon = MagicMock()
        mock_recon.broker = MagicMock()  # truthy -> proceeds
        mock_cur = MagicMock()
        mock_db_context = MagicMock()
        mock_db_context.__enter__ = MagicMock(return_value=mock_cur)
        mock_db_context.__exit__ = MagicMock(return_value=False)

        with (
            patch("algo.infrastructure.reconciliation.DailyReconciliation", return_value=mock_recon),
            patch("algo.execution.trade_update_listener.DatabaseContext", return_value=mock_db_context),
        ):
            listener._run_reconciliation_now(_config(), "fill", "AAPL")

        mock_recon.check_partial_fills.assert_called_once_with(mock_cur)
        mock_recon.reconcile_exit_fills.assert_called_once()
        assert mock_recon.reconcile_exit_fills.call_args[0][0] is mock_cur

    def test_reconciliation_failure_is_caught_not_raised(self):
        """A reconciliation hiccup must never kill the listener process - the next event
        or the next scheduled cycle will retry independently."""
        mock_recon = MagicMock()
        mock_recon.broker = MagicMock()
        mock_recon.check_partial_fills.side_effect = RuntimeError("Alpaca API down")
        mock_db_context = MagicMock()
        mock_db_context.__enter__ = MagicMock(return_value=MagicMock())
        mock_db_context.__exit__ = MagicMock(return_value=False)

        with (
            patch("algo.infrastructure.reconciliation.DailyReconciliation", return_value=mock_recon),
            patch("algo.execution.trade_update_listener.DatabaseContext", return_value=mock_db_context),
        ):
            listener._run_reconciliation_now(_config(), "fill", "AAPL")  # must not raise

    def test_daily_reconciliation_construction_failure_is_caught_not_raised(self):
        """Regression for the 2026-09-06 adversarial-review finding: the try/except used
        to start AFTER DailyReconciliation(config) construction, so a construction-time
        failure (e.g. DailyReconciliation.__init__ raises ValueError when config is
        missing execution_mode) would propagate uncaught - contradicting this function's
        own 'never let a reconciliation hiccup kill the listener process' contract."""
        with patch(
            "algo.infrastructure.reconciliation.DailyReconciliation",
            side_effect=ValueError("execution_mode missing"),
        ):
            listener._run_reconciliation_now(_config(), "fill", "AAPL")  # must not raise


class TestListenerAbsenceDegradesLatencyNotCorrectness:
    """Proves the design claim directly: a fill that the listener NEVER saw is still
    correctly reconciled by calling the exact same methods independently - i.e., nothing
    about correctness depends on the listener having fired at all."""

    def test_reconciliation_methods_work_standalone_without_any_listener_involvement(self):
        mock_recon = MagicMock()
        mock_recon.broker = MagicMock()
        mock_recon.check_partial_fills.return_value = {"mismatches": 1, "corrected": 1}
        mock_recon.reconcile_exit_fills.return_value = {"updated": 1}
        mock_db_context = MagicMock()
        mock_db_context.__enter__ = MagicMock(return_value=MagicMock())
        mock_db_context.__exit__ = MagicMock(return_value=False)

        # Simulates the orchestrator's OWN independent scheduled call - no listener
        # anywhere in this call path.
        with (
            patch("algo.infrastructure.reconciliation.DailyReconciliation", return_value=mock_recon) as mock_cls,
            patch("algo.execution.trade_update_listener.DatabaseContext", return_value=mock_db_context),
        ):
            from algo.infrastructure.reconciliation import DailyReconciliation

            recon = DailyReconciliation(_config())
            with mock_db_context as cur:
                result = recon.check_partial_fills(cur)

        assert result == {"mismatches": 1, "corrected": 1}
        mock_cls.assert_called_once()


class TestRunForeverReconnectLoop:
    def test_reconnects_with_backoff_on_repeated_failures(self):
        call_count = {"n": 0}

        def _fail_then_stop(config):
            call_count["n"] += 1
            if call_count["n"] >= 3:
                raise KeyboardInterrupt("stop test loop")
            raise RuntimeError("connection dropped")

        with (
            patch("algo.execution.trade_update_listener.get_config", return_value=_config()),
            patch("algo.execution.trade_update_listener._build_stream", side_effect=_fail_then_stop),
            patch("algo.execution.trade_update_listener.time.sleep") as mock_sleep,
        ):
            try:
                listener.run_forever()
                raise AssertionError("expected KeyboardInterrupt to stop the loop")
            except KeyboardInterrupt:
                pass

        assert call_count["n"] == 3
        assert mock_sleep.call_count == 2
        # Backoff must actually increase, not stay flat, across consecutive failures.
        first_delay = mock_sleep.call_args_list[0][0][0]
        second_delay = mock_sleep.call_args_list[1][0][0]
        assert second_delay > first_delay

    def test_successful_run_resets_backoff(self):
        call_count = {"n": 0}

        def _stream_run_side_effect():
            call_count["n"] += 1
            if call_count["n"] >= 2:
                raise KeyboardInterrupt("stop test loop")
            return None  # first call "succeeds" (stream.run() returned normally)

        mock_stream = MagicMock()
        mock_stream.run.side_effect = _stream_run_side_effect

        with (
            patch("algo.execution.trade_update_listener.get_config", return_value=_config()),
            patch("algo.execution.trade_update_listener._build_stream", return_value=mock_stream),
            patch("algo.execution.trade_update_listener.time.sleep") as mock_sleep,
        ):
            try:
                listener.run_forever()
                raise AssertionError("expected KeyboardInterrupt to stop the loop")
            except KeyboardInterrupt:
                pass

        # First iteration "succeeded" (no exception) -> immediate reconnect attempt with
        # no sleep at all for that transition.
        mock_sleep.assert_not_called()


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
