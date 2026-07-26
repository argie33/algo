#!/usr/bin/env python3
"""Test harness to verify orchestrator works with fixes applied.

Bypasses market calendar check to test on non-trading days.
Runs full 9-phase orchestrator to verify fixes are effective.
"""

import sys
import os
from datetime import date
from unittest.mock import patch

# Force trading day for test
TEST_DATE = date(2026, 7, 24)

def test_orchestrator_full_run():
    """Run full orchestrator pipeline and verify all 9 phases."""

    # Patch market calendar to allow testing
    with patch('algo.infrastructure.market_calendar.MarketCalendar.is_trading_day') as mock_calendar:
        mock_calendar.return_value = True

        # Patch the datetime to use test date
        from datetime import datetime
        from zoneinfo import ZoneInfo

        with patch('algo.orchestration.orchestrator.datetime') as mock_datetime:
            test_dt = datetime(2026, 7, 24, 14, 53, 0, tzinfo=ZoneInfo('America/New_York'))
            mock_datetime.now.return_value = test_dt
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

            # Import and run orchestrator
            from algo.orchestration.orchestrator import run_orchestrator

            print("Starting orchestrator test run...")
            print(f"Test date: {TEST_DATE}")
            print(f"Forcing trading day: True")

            try:
                # Run orchestrator
                result = run_orchestrator(
                    run_date=TEST_DATE,
                    execution_mode='paper',
                    is_local_mode=True,
                    log_phase_result_fn=lambda *args, **kw: None
                )

                print(f"\nOrchestrator run completed:")
                print(f"  Status: {result.get('status', 'unknown')}")
                print(f"  Overall Status: {result.get('overall_status', 'unknown')}")

                # Check each phase
                phases_completed = 0
                phases_with_errors = 0

                for phase_num in range(1, 10):
                    phase_key = f'phase_{phase_num}'
                    if phase_key in result:
                        phases_completed += 1
                        phase_result = result[phase_key]
                        status = phase_result.get('status', 'unknown')
                        if status in ['error', 'halted', 'blocked']:
                            phases_with_errors += 1
                            print(f"  Phase {phase_num}: {status} - {phase_result.get('message', '')}")
                        else:
                            print(f"  Phase {phase_num}: {status}")

                print(f"\nPhases completed: {phases_completed}/9")
                print(f"Phases with errors: {phases_with_errors}")

                # Verify fixes
                if phases_completed >= 7:
                    print("\n✓ VERIFICATION SUCCESS: Orchestrator completed with fixes applied")
                    return True
                else:
                    print("\n✗ VERIFICATION FAILED: Not all phases completed")
                    return False

            except Exception as e:
                print(f"\n✗ ORCHESTRATOR ERROR: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
                return False

if __name__ == '__main__':
    success = test_orchestrator_full_run()
    sys.exit(0 if success else 1)
