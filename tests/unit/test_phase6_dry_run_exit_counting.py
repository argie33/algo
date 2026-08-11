"""Test that Phase 6 counts exits correctly in dry-run mode."""

from unittest.mock import MagicMock, patch

import pytest

from algo.orchestrator.phase6_exit_execution import run as phase6_run
from algo.orchestrator.phase_result import PhaseResult


def test_phase6_dry_run_counts_exits():
    """Verify Phase 6 counts exits in dry-run mode and includes data in result."""
    config = {
        "execution_mode": "paper",
        "alpaca_paper_trading": True,
        "max_positions_per_sector": 10,
        "max_position_size_pct": 6.0,
    }

    # Mock position recs with EARLY_EXIT actions
    position_recs = [
        {
            "symbol": "AAPL",
            "action": "EARLY_EXIT",
            "trade_id": "trade_1",
            "current_price": 150.0,
            "action_reason": "profit_target",
            "position_id": "pos_1",
        },
        {
            "symbol": "GOOGL",
            "action": "EARLY_EXIT",
            "trade_id": "trade_2",
            "current_price": 140.0,
            "action_reason": "time_exit",
            "position_id": "pos_2",
        },
        {
            "symbol": "MSFT",
            "action": "RAISE_STOP",
            "trade_id": "trade_3",
            "new_stop_recommended": 300.0,
            "active_stop": 295.0,
            "position_id": "pos_3",
        },
    ]

    exposure_actions = [
        {
            "symbol": "TSLA",
            "action": "force_exit",
            "trade_id": "trade_4",
            "reason": "sector_drawdown",
            "position_id": "pos_4",
        },
    ]

    alert_manager = MagicMock()
    log_phase_result_fn = MagicMock()

    # Mock DatabaseContext for position price fetching
    with patch("algo.orchestrator.phase6_exit_execution.DatabaseContext") as mock_db:
        # Set up mock cursor with side_effect for multiple queries
        mock_cursor = MagicMock()
        # Configure fetchone responses for: orphaned-trade validation + concentration checks
        # + force_exit price fetches. run() does an orphaned-trade DELETE first (reads
        # cur.rowcount, not fetchone - see rowcount=0 below), then a separate
        # SELECT COUNT(*) validation query that DOES consume a fetchone() - that must be
        # first in this list or every later fetchone() shifts by one and the shapes stop
        # matching what each query actually expects.
        mock_cursor.fetchone.side_effect = [
            (0,),  # Orphaned-trade validation count query
            (0, 0),  # Sector concentration check - count query
            (0,),  # Sector concentration check - SUM query
            (0, 0),  # Size concentration check - count query
            (0,),  # Size concentration check - SUM query
            (150.0,),  # current_price for force_exit
        ]
        mock_cursor.fetchall.return_value = []  # No positions for concentration check (empty portfolio)
        mock_cursor.rowcount = 0  # No orphaned trades deleted by the cleanup DELETE
        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_cursor
        mock_context.__exit__.return_value = None
        mock_db.return_value = mock_context

        # Run phase 6 in dry-run mode
        result = phase6_run(
            config=config,
            run_date=__import__("datetime").date.today(),
            dry_run=True,
            alerts=alert_manager,
            verbose=False,
            log_phase_result_fn=log_phase_result_fn,
            position_recs=position_recs,
            exposure_actions=exposure_actions,
            check_halt_flag=None,
        )

    # Verify result is PhaseResult
    assert isinstance(result, PhaseResult)

    # Verify status is degraded (expected for dry-run)
    assert result.status == "degraded"

    # Verify data dict is NOT empty (this is the key fix!)
    assert result.data is not None
    assert isinstance(result.data, dict)
    assert len(result.data) > 0, "Phase 6 dry-run should return data with exit counts"

    # Verify exit counts are present
    assert "exits" in result.data or "exits_executed" in result.data, "Phase 6 result should include exit count"
    assert "stop_raises" in result.data, "Phase 6 result should include stop_raises count"

    # Verify the counts are reasonable
    # We had 2 EARLY_EXIT + 1 force_exit = 3 exits
    # We had 1 RAISE_STOP = 1 stop_raise
    exits = result.data.get("exits") or result.data.get("exits_executed", 0)
    stops = result.data.get("stop_raises", 0)

    assert exits >= 2, f"Expected at least 2 exits in dry-run, got {exits}"
    assert stops >= 1, f"Expected at least 1 stop-raise in dry-run, got {stops}"

    # Verify log_phase_result_fn was called with proper arguments
    log_phase_result_fn.assert_called_once()
    call_args = log_phase_result_fn.call_args
    assert call_args[0][1] == "exit_execution"  # phase name
    assert call_args[0][2] == "degraded"  # status
    assert "DRY-RUN" in str(call_args[0][3]), "Detail text should mention DRY-RUN"


def test_phase6_dry_run_returns_degraded_status():
    """Verify Phase 6 returns 'degraded' status in dry-run mode (expected behavior)."""
    config = {
        "execution_mode": "paper",
        "alpaca_paper_trading": True,
        "max_positions_per_sector": 10,
        "max_position_size_pct": 6.0,
    }

    position_recs = []
    exposure_actions = []

    alert_manager = MagicMock()
    log_phase_result_fn = MagicMock()

    with patch("algo.orchestrator.phase6_exit_execution.DatabaseContext") as mock_db:
        # Set up mock cursor for concentration checks with empty portfolio
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [
            (0,),  # Orphaned-trade validation count query
            (0, 0),  # Sector concentration check - count query
            (0,),  # Sector concentration check - SUM query
            (0, 0),  # Size concentration check - count query
            (0,),  # Size concentration check - SUM query
        ]
        mock_cursor.fetchall.return_value = []  # No positions for concentration checks
        mock_cursor.rowcount = 0  # No orphaned trades deleted by the cleanup DELETE
        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_cursor
        mock_context.__exit__.return_value = None
        mock_db.return_value = mock_context

        result = phase6_run(
            config=config,
            run_date=__import__("datetime").date.today(),
            dry_run=True,
            alerts=alert_manager,
            verbose=False,
            log_phase_result_fn=log_phase_result_fn,
            position_recs=position_recs,
            exposure_actions=exposure_actions,
            check_halt_flag=None,
        )

    # In dry-run mode, status should always be 'degraded' (execution skipped)
    assert result.status == "degraded"

    # Data should still be present with zero counts
    assert result.data is not None
    assert "exits" in result.data or "exits_executed" in result.data
    exits = result.data.get("exits") or result.data.get("exits_executed", 0)
    assert exits == 0, "No exits in empty position_recs"


if __name__ == "__main__":
    test_phase6_dry_run_counts_exits()
    test_phase6_dry_run_returns_degraded_status()
    print("✓ All tests passed!")
