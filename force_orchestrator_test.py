#!/usr/bin/env python3
"""Force orchestrator execution for testing by mocking market calendar"""

import sys
from unittest.mock import patch
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

# Mock MarketCalendar.is_trading_day to return True
def mock_is_trading_day(check_date):
    """Mock: always return True for testing"""
    return True

def mock_get_previous_trading_day(ref_date):
    """Mock: return previous day for testing"""
    from datetime import timedelta
    return ref_date - timedelta(days=1)

print("=" * 90)
print("FORCING ORCHESTRATOR EXECUTION FOR FULL SYSTEM TEST")
print("=" * 90)

# Patch before importing orchestrator
with patch('algo.infrastructure.MarketCalendar.is_trading_day', side_effect=mock_is_trading_day):
    with patch('algo.infrastructure.MarketCalendar.get_previous_trading_day', side_effect=mock_get_previous_trading_day):
        with patch('algo.orchestration.orchestrator.MarketCalendar.is_trading_day', side_effect=mock_is_trading_day):
            print("\nMarket calendar mocked - forcing orchestrator to run...")

            from algo.orchestration import Orchestrator
            from algo.infrastructure.config import AlgoConfig
            from datetime import date

            # Create orchestrator with mocked calendar
            config = AlgoConfig()
            run_date = date(2026, 7, 31)  # Use Friday (actual trading day)

            print(f"\nRunning orchestrator for {run_date} (dry_run=True for outside market hours)...")
            orch = Orchestrator(config, run_date, dry_run=True)

            try:
                result = orch.run()

                print("\n" + "=" * 90)
                print("ORCHESTRATOR EXECUTION RESULT")
                print("=" * 90)
                print(f"Overall status: {result.get('overall_status')}")
                print(f"Phases completed: {result.get('phases_completed')}")
                print(f"Phases halted: {result.get('phases_halted')}")
                print(f"Phases errored: {result.get('phases_errored')}")

                if 'phase_results' in result and result['phase_results']:
                    print("\nPhase Results:")
                    for phase in result['phase_results']:
                        status = phase.get('status', '?')
                        name = phase.get('name', 'unknown')
                        print(f"  Phase {phase.get('phase', '?')}: {name:30} - {status}")

                print("\n" + "=" * 90)
                if result.get('overall_status') == 'success':
                    print("SUCCESS: All 9 phases completed")
                    print("Orchestrator is working correctly!")
                elif result.get('overall_status') == 'halted':
                    print("HALTED: One or more phases halted")
                    if 'halt_reason' in result:
                        print(f"Reason: {result['halt_reason']}")
                else:
                    print(f"STATUS: {result.get('overall_status')}")
                print("=" * 90)

            except Exception as e:
                print(f"\nERROR: Orchestrator execution failed")
                print(f"Exception: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
                sys.exit(1)
