"""Regression test: Phase 6 must count/log positions that failed Phase 3 validation.

algo/monitoring/position_monitor.py appends a {"action": "FAILED_VALIDATION", "error": ...}
rec (no action_reason/current_price/new_stop_recommended) whenever PositionValidationError is
raised while evaluating a position - e.g. bad quantity, bad entry price, corrupted stop/target
data. Confirmed live 2026-07-27: neither the EARLY_EXIT nor RAISE_STOP branch in Phase 6's
position_recs loop matched "FAILED_VALIDATION", so the rec fell through with no error counted
and no log - a position too data-corrupt to even evaluate got silently zero exit/stop coverage
for the run, with Phase 6 still reporting "0 errors" / status "ok". This pins the fix: the rec
must be counted as an error and logged.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.orchestrator import phase6_exit_execution as p6


def _make_config():
    return {
        "execution_mode": "paper",
        "alpaca_paper_trading": True,
    }


def test_failed_validation_rec_counted_as_error_not_silently_dropped():
    config = _make_config()
    position_recs = [
        {
            "trade_id": "TRD-BAD",
            "symbol": "ZZZZ",
            "position_id": 999,
            "action": "FAILED_VALIDATION",
            "error": "Invalid quantity for ZZZZ: -5 <= 0",
        }
    ]

    with (
        patch("algo.trading.executor.TradeExecutor") as mock_executor_cls,
        patch("algo.trading.ExitEngine") as mock_engine_cls,
    ):
        mock_executor_cls.return_value = MagicMock()
        mock_engine = MagicMock()
        mock_engine.check_and_execute_exits.return_value = (0, 0, 0)
        mock_engine_cls.return_value = mock_engine

        result = p6.run(
            config=config,
            run_date=date(2026, 7, 27),
            dry_run=False,
            alerts=MagicMock(),
            verbose=False,
            log_phase_result_fn=MagicMock(),
            position_recs=position_recs,
            exposure_actions=[],
            check_halt_flag=None,
        )

    assert result.data["errors"] == 1
    assert result.status == "degraded"
