"""Regression test: Phase 6 must alert when exit-check errors occur.

phase6_exit_execution.run() receives an AlertManager (`alerts`) exactly like Phase 2
(circuit breakers) and Phase 3 (position monitor), both of which call
alerts.send_position_alert() for analogous issues - but Phase 6 never called it at all.
A degraded exit-execution status (positions that lost stop/target/time-exit coverage for
the run) was visible only to something polling orchestrator_execution_log, never pushed to
an operator. This pins the fix: errors > 0 must trigger exactly one aggregate alert, and
errors == 0 must not alert at all.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.orchestrator import phase6_exit_execution as p6


def _make_config():
    return {
        "execution_mode": "paper",
        "alpaca_paper_trading": True,
        "max_positions_per_sector": 10,
        "max_exposure_pct": 100,
    }


def test_alert_sent_when_exit_errors_occur():
    config = _make_config()
    mock_alerts = MagicMock()

    with (
        patch("algo.trading.executor.TradeExecutor") as mock_executor_cls,
        patch("algo.trading.ExitEngine") as mock_engine_cls,
        patch("algo.orchestrator.phase6_exit_execution.DatabaseContext") as mock_db_ctx,
    ):
        mock_executor_cls.return_value = MagicMock()
        mock_engine = MagicMock()
        mock_engine.check_and_execute_exits.return_value = (0, 0, 3, 0)
        mock_engine_cls.return_value = mock_engine

        # Mock the open position count check to return 0 open positions
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (0,)  # No open positions
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False

        result = p6.run(
            config=config,
            run_date=date(2026, 7, 27),
            dry_run=False,
            alerts=mock_alerts,
            verbose=False,
            log_phase_result_fn=MagicMock(),
            position_recs=[],
            exposure_actions=[],
            check_halt_flag=None,
        )

    assert result.data["errors"] == 3
    assert result.status == "degraded"
    mock_alerts.send_position_alert.assert_called_once()
    call_args = mock_alerts.send_position_alert.call_args
    assert call_args.args[1] == "EXIT_CHECK_FAILURES"
    assert "3" in call_args.args[2]


def test_no_alert_when_no_exit_errors():
    config = _make_config()
    mock_alerts = MagicMock()

    with (
        patch("algo.trading.executor.TradeExecutor") as mock_executor_cls,
        patch("algo.trading.ExitEngine") as mock_engine_cls,
        patch("algo.orchestrator.phase6_exit_execution.DatabaseContext") as mock_db_ctx,
    ):
        mock_executor_cls.return_value = MagicMock()
        mock_engine = MagicMock()
        mock_engine.check_and_execute_exits.return_value = (2, 1, 0, 0)
        mock_engine_cls.return_value = mock_engine

        # Mock the open position count check to return 0 open positions
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (0,)  # No open positions
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False

        result = p6.run(
            config=config,
            run_date=date(2026, 7, 27),
            dry_run=False,
            alerts=mock_alerts,
            verbose=False,
            log_phase_result_fn=MagicMock(),
            position_recs=[],
            exposure_actions=[],
            check_halt_flag=None,
        )

    assert result.data["errors"] == 0
    mock_alerts.send_position_alert.assert_not_called()
