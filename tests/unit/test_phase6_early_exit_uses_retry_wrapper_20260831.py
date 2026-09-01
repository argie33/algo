#!/usr/bin/env python3
"""Regression test for the 2026-08-31 (/goal pre-real-money audit) fix: Phase 6's EARLY_EXIT
branch (position_monitor's stop-loss-hit/target-hit/health-flag-forced exits - the highest-stakes
exit path in this file) used to call trade_executor.exit_trade() directly instead of going
through _retry_exit_trade(), unlike both exposure_actions branches in the same file which already
used the wrapper correctly.

Two compounding problems this caused: (1) a transient TimeoutError/ConnectionError/OSError during
the actual exit call got zero retry, unlike every other exit path in this file; (2) the loop's own
`except (RuntimeError, ValueError, TypeError, AttributeError)` does not include those three
transient types, so such an error propagated straight out of run() uncaught - crashing the entire
Phase 6 execution mid-loop rather than failing just that one position.

This test verifies the WIRING - that _retry_exit_trade (not the raw executor method) is the
function actually invoked for an EARLY_EXIT recommendation - rather than trying to reproduce
timing-sensitive retry/backoff behavior end-to-end (_retry_exit_trade's own retry semantics are
already covered by test_phase6_retry_exit_trade_and_response_validation_20260824.py).
"""

from datetime import date
from unittest.mock import MagicMock, patch


def _config():
    return {
        "execution_mode": "paper",
        "alpaca_paper_trading": True,
        "max_positions_per_sector": 10,
        "max_position_size_pct": 6.0,
        # Required by ExitEngine's own init validation, unrelated to this test's focus
        # (the EARLY_EXIT branch runs and returns before ExitEngine is even reached, but
        # run() initializes it unconditionally later in the same call).
        "min_hold_days": 1,
        "max_hold_days": 90,
        "eight_week_rule_threshold_pct": 5.0,
        "eight_week_rule_window_days": 56,
        "exit_on_distribution_day": False,
        "max_distribution_days": 5,
        "move_be_at_r": 1.0,
        "chandelier_atr_mult": 3.0,
        "t1_target_r_multiple": 1.0,
        "t2_target_r_multiple": 2.0,
        "t3_target_r_multiple": 3.0,
    }


def _mock_db_context():
    mock_cursor = MagicMock()
    # Orphaned-trade validation count, sector concentration count+SUM, size concentration
    # count+SUM - the same fixed sequence every non-dry-run pass through run() executes
    # before reaching the EARLY_EXIT loop, regardless of position_recs content (matches
    # test_phase6_dry_run_exit_counting.py's own documented sequence).
    mock_cursor.fetchone.side_effect = [
        (0,),
        (0, 0),
        (0,),
        (0, 0),
        (0,),
    ]
    mock_cursor.fetchall.return_value = []
    mock_cursor.rowcount = 0
    mock_context = MagicMock()
    mock_context.__enter__.return_value = mock_cursor
    mock_context.__exit__.return_value = None
    return mock_context


class TestEarlyExitUsesRetryWrapper:
    def test_early_exit_calls_retry_wrapper_not_raw_exit_trade(self):
        from algo.orchestrator.phase6_exit_execution import run as phase6_run

        position_recs = [
            {
                "symbol": "AAPL",
                "action": "EARLY_EXIT",
                "trade_id": "trade_1",
                "current_price": 150.0,
                "action_reason": "stop_loss_hit",
                "position_id": "pos_1",
            }
        ]

        with (
            patch("algo.orchestrator.phase6_exit_execution.DatabaseContext", return_value=_mock_db_context()),
            patch("algo.trading.executor.TradeExecutor") as MockTradeExecutor,
            patch("algo.orchestrator.phase6_exit_execution._retry_exit_trade") as mock_retry_exit_trade,
        ):
            mock_executor_instance = MockTradeExecutor.return_value
            mock_retry_exit_trade.return_value = {
                "success": True,
                "trade_id": "trade_1",
                "message": "ok",
                "executed_price": 150.0,
                "filled_qty": 10,
            }

            # Return value deliberately not inspected here - see comment below on why.
            phase6_run(
                config=_config(),
                run_date=date(2026, 8, 31),
                dry_run=False,
                alerts=MagicMock(),
                verbose=False,
                log_phase_result_fn=MagicMock(),
                position_recs=position_recs,
                exposure_actions=[],
                check_halt_flag=None,
            )

        # These are the load-bearing assertions for this regression test - the EARLY_EXIT
        # loop itself already ran and completed successfully by the time run() reaches this
        # point (later, unrelated ExitEngine/reconciliation config requirements can still halt
        # the overall phase result afterward - not this fix's concern, so `result` itself is
        # deliberately not asserted on further here).
        assert mock_retry_exit_trade.call_count == 1, (
            "EARLY_EXIT must go through _retry_exit_trade (the same wrapper both "
            "exposure_actions branches already use), not call executor.exit_trade() directly"
        )
        assert mock_retry_exit_trade.call_args.kwargs["trade_id"] == "trade_1"
        # The raw executor method must NOT have been called directly for this trade - only
        # _retry_exit_trade should be invoking it internally (mocked out here entirely).
        mock_executor_instance.exit_trade.assert_not_called()


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
