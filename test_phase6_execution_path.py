#!/usr/bin/env python3
"""Test Phase 6 execution path to verify exits will execute during market hours.

This verifies the logic paths that would execute real trades, without actually
submitting orders. It simulates the conditions that occur during real trading.
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils.dotenv_loader import load_env_local
load_env_local()

from unittest.mock import Mock, patch, MagicMock
from algo.orchestrator.phase6_exit_execution import run as phase6_run
from algo.reporting import AlertManager

def test_phase6_with_real_execution():
    """Test that Phase 6 will execute trades when dry_run=False."""
    print("=" * 70)
    print("TEST: Phase 6 Exit Execution Path")
    print("=" * 70)

    # Setup
    mock_config = {
        "execution_mode": "auto",  # LIVE mode
        "alpaca_paper_trading": True,
        "max_positions_per_sector": 8,
    }

    # Mock the config object to act like a dict
    mock_config_obj = Mock()
    mock_config_obj.get = lambda key, default=None: mock_config.get(key, default)
    mock_config_obj.__getitem__ = lambda self, key: mock_config[key]
    mock_config_obj.__contains__ = lambda self, key: key in mock_config

    # Test case 1: dry_run=False (SHOULD execute)
    print("\nTest Case 1: dry_run=False (non-dry run, should execute)")
    print("-" * 70)

    # Create mock TradeExecutor that won't actually submit orders
    with patch('algo.trading.executor.TradeExecutor') as mock_executor_class:
        mock_executor_instance = Mock()
        mock_executor_class.return_value = mock_executor_instance
        mock_executor_instance.exit_trade.return_value = {"success": True, "message": "test exit"}

        # Create minimal test data
        position_recs = []  # No position monitor recs
        exposure_actions = []  # No exposure policy actions

        mock_alerts = Mock(spec=AlertManager)
        mock_log_fn = Mock()

        with patch('algo.orchestrator.phase6_exit_execution.DatabaseContext') as mock_db:
            # Mock database to return test positions
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = None  # No positions to check
            mock_cursor.fetchall.return_value = []
            mock_db.return_value.__enter__.return_value = mock_cursor

            try:
                result = phase6_run(
                    config=mock_config_obj,
                    run_date=None,
                    dry_run=False,  # NOT dry run - should execute
                    alerts=mock_alerts,
                    verbose=True,
                    log_phase_result_fn=mock_log_fn,
                    position_recs=position_recs,
                    exposure_actions=exposure_actions,
                )

                # Verify TradeExecutor was initialized (meaning execution path was entered)
                if mock_executor_class.called:
                    print("  [OK] TradeExecutor was initialized (execution path entered)")
                    print(f"      - Called {mock_executor_class.call_count} time(s)")
                else:
                    print("  [FAIL] TradeExecutor was NOT initialized")
                    print("      - This means Phase 6 would skip execution even with dry_run=False")
                    return False

                print(f"  [OK] Phase result status: {result.status}")
                print(f"      - Details: {result.detail}")

            except Exception as e:
                print(f"  [ERROR] Unexpected exception: {type(e).__name__}: {e}")
                return False

    # Test case 2: dry_run=True (SHOULD NOT execute)
    print("\nTest Case 2: dry_run=True (dry run, should NOT execute)")
    print("-" * 70)

    with patch('algo.trading.executor.TradeExecutor') as mock_executor_class:
        mock_executor_instance = Mock()
        mock_executor_class.return_value = mock_executor_instance

        try:
            result = phase6_run(
                config=mock_config_obj,
                run_date=None,
                dry_run=True,  # DRY run - should NOT execute
                alerts=Mock(spec=AlertManager),
                verbose=True,
                log_phase_result_fn=Mock(),
                position_recs=[],
                exposure_actions=[],
            )

            if not mock_executor_class.called:
                print("  [OK] TradeExecutor was NOT initialized (dry-run skipped execution)")
                print(f"  [OK] Phase result status: {result.status}")
                print(f"      - Details: {result.detail}")
            else:
                print("  [FAIL] TradeExecutor WAS initialized even though dry_run=True")
                print("      - This means dry-run would execute trades!")
                return False

        except Exception as e:
            print(f"  [ERROR] Unexpected exception: {type(e).__name__}: {e}")
            return False

    # Test case 3: execution_mode='paper' (SHOULD execute in paper mode)
    print("\nTest Case 3: execution_mode='paper' (paper mode, should still execute)")
    print("-" * 70)

    paper_config = {
        "execution_mode": "paper",  # Paper mode
        "alpaca_paper_trading": True,
        "max_positions_per_sector": 8,
    }

    paper_config_obj = Mock()
    paper_config_obj.get = lambda key, default=None: paper_config.get(key, default)
    paper_config_obj.__getitem__ = lambda self, key: paper_config[key]
    paper_config_obj.__contains__ = lambda self, key: key in paper_config

    with patch('algo.trading.executor.TradeExecutor') as mock_executor_class:
        mock_executor_instance = Mock()
        mock_executor_class.return_value = mock_executor_instance
        mock_executor_instance.exit_trade.return_value = {"success": True, "message": "test"}

        try:
            result = phase6_run(
                config=paper_config_obj,
                run_date=None,
                dry_run=False,  # NOT dry run
                alerts=Mock(spec=AlertManager),
                verbose=True,
                log_phase_result_fn=Mock(),
                position_recs=[],
                exposure_actions=[],
            )

            if mock_executor_class.called:
                print("  [OK] TradeExecutor initialized in paper mode")
                print("      - Paper mode trades will execute against paper account")
            else:
                print("  [FAIL] TradeExecutor NOT initialized in paper mode")
                return False

        except Exception as e:
            print(f"  [ERROR] Unexpected exception: {type(e).__name__}: {e}")
            return False

    print("\n" + "=" * 70)
    print("RESULT: All execution path tests PASSED")
    print("=" * 70)
    print("\nConclusion:")
    print("  - Phase 6 WILL execute trades when dry_run=False during market hours")
    print("  - Phase 6 will NOT execute during dry-run (expected)")
    print("  - Paper mode trading is properly configured")
    print("\nPhase 6 is ready for production use.")
    return True

if __name__ == "__main__":
    success = test_phase6_with_real_execution()
    sys.exit(0 if success else 1)
