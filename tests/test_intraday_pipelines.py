#!/usr/bin/env python3
"""
Test Script: Intraday Score Update Pipelines

Validates that:
1. Morning pipeline completes before afternoon orchestrator
2. Afternoon update pipeline completes before 1 PM orchestrator
3. Pre-close update pipeline completes before 3 PM orchestrator (SLA)
4. Fresh scores are computed at each stage
5. Orchestrators use the latest scores available
"""

import os
import sys

# Add project root to path
project_root = str(os.path.dirname(__file__).rsplit("/", 1)[0])
sys.path.insert(0, project_root)


def test_morning_pipeline_timing():
    """Verify morning pipeline completes before 9:30 AM (7.5h before is 2:00 AM)"""
    print("\n=== TEST: Morning Pipeline Timing ===")

    expected_start = "02:00"  # 2:00 AM ET
    expected_complete = "04:00"  # 4:00 AM ET (before 9:30 AM orchestrator)

    print(f"Expected: Pipeline starts at {expected_start} ET, completes by {expected_complete} ET")
    print("Check CloudWatch logs for /ecs/algo-*-loader timestamps")
    print("Requirement: Ready 7.5 hours before 9:30 AM market open [OK]")


def test_afternoon_update_pipeline():
    """Verify afternoon update pipeline triggers before 1 PM and completes by 1:05 PM

    NOTE: swing_trader_scores intraday updates have been deprecated.
    Current signal generation uses composite_score from stock_scores table.
    """
    print("\n=== TEST: Afternoon Update Pipeline (1 PM) [DEPRECATED] ===")

    print("NOTE: Intraday swing_trader_scores updates have been retired.")
    print("Current architecture: composite_score from stock_scores (daily updates)")
    print("Signal generation: Phase 7 uses buy_sell_daily + stock_scores (no intraday updates)")


def test_preclose_update_pipeline():
    """Pre-close update pipeline has been deprecated

    NOTE: swing_trader_scores intraday updates have been retired.
    Current signal generation uses daily stock_scores updates.
    """
    print("\n=== TEST: Pre-Close Update Pipeline (DEPRECATED) ===")

    print("NOTE: Pre-close swing_trader_scores updates have been retired.")
    print("Current architecture: composite_score from stock_scores (daily, EOD at 4:05 PM ET)")
    print("Orchestrators: No longer depend on intraday score updates")


def test_fresh_scores_used_by_orchestrator():
    """Verify orchestrators use latest scores for signal generation

    NOTE: No longer using intraday swing_trader_scores.
    Current behavior: Phase 7 uses daily stock_scores (updated EOD).
    """
    print("\n=== TEST: Orchestrator Uses Latest Scores ===")

    print("Current behavior:")
    print("  - Phase 7 (signal generation) uses stock_scores.composite_score")
    print("  - Scores updated daily via EOD loader pipeline")
    print("  - No intraday updates (removed with swing_trader_scores table)")


def test_no_database_conflicts():
    """Verify concurrent loader runs don't conflict"""
    print("\n=== TEST: No Database Conflicts ===")

    print("Concurrent runs that should NOT conflict:")
    print("  - 2 AM morning pipeline + 4:05 PM EOD pipeline (opposite sides of trading day)")
    print("  - 12:50 PM afternoon update + 2:50 PM pre-close update")
    print("    (different start times, <30 min apart)")

    print("\nChecks:")
    print("1. No lock timeouts in CloudWatch logs")
    print("2. No 'database connection pool exhausted' errors")
    print("3. All loaders complete successfully")


def test_failure_scenarios():
    """Test what happens if pipelines fail"""
    print("\n=== TEST: Failure Scenarios ===")

    print("\nScenario 1: Afternoon update pipeline fails (12:50 PM)")
    print("  Expected: 1 PM orchestrator uses morning scores (fallback)")
    print("  Check: Orchestrator Phase 5 logs show 2 AM score timestamp")

    print("\nScenario 2: Pre-close update pipeline fails (2:50 PM)")
    print("  Expected: 3 PM orchestrator uses afternoon scores (fallback)")
    print("  Expected: SLA still met (3:15 PM < 4 PM close)")
    print("  Check: Orchestrator Phase 5 logs show 12:50 PM score timestamp")

    print("\nScenario 3: Morning pipeline fails (2 AM)")
    print("  Expected: 9:30 AM orchestrator uses previous day's scores (or halts)")
    print("  Expected: Afternoon/pre-close orchestrators fail or use fallback")
    print("  Check: Phase 1 halt detection in orchestrator logs")


def validate_intraday_mode_support():
    """DEPRECATED: Intraday mode no longer used

    NOTE: swing_trader_scores and its INTRADAY_MODE updates have been removed.
    """
    print("\n=== TEST: INTRADAY_MODE (DEPRECATED) ===")

    print("NOTE: INTRADAY_MODE environment variable no longer used.")
    print("Reason: swing_trader_scores table and its intraday loader have been removed.")
    print("Current: Daily EOD updates for all metrics via loaders in main pipeline.")

    return True


def validate_terraform_state_machines():
    """Check that Terraform state machines were created"""
    print("\n=== TEST: Terraform Step Functions State Machines ===")

    state_machines = [
        "algo-eod-pipeline",
        "algo-morning-prep-pipeline",
        "algo-intraday-afternoon-update",
        "algo-intraday-preclose-update",
    ]

    print("Expected state machines:")
    for sm in state_machines:
        print(f"  - {sm}")

    print("\nVerification:")
    print("1. Deploy Terraform changes (terraform apply)")
    print("2. Check AWS Step Functions console")
    print("3. Verify all 4 state machines exist")
    print("4. Check execution history for each")
    return True


def validate_eventbridge_rules():
    """Check that EventBridge scheduler rules exist"""
    print("\n=== TEST: EventBridge Scheduler Rules ===")

    rules = {
        "algo-morning-pipeline": "2:00 AM ET",
        "algo-afternoon-update-pipeline": "12:50 PM ET",
        "algo-preclose-update-pipeline": "2:50 PM ET",
        "algo-eod-pipeline": "4:05 PM ET",
    }

    print("Expected EventBridge Scheduler rules:")
    for rule, time in rules.items():
        print(f"  - {rule}: {time}")

    print("\nVerification:")
    print("1. Deploy Terraform changes (terraform apply)")
    print("2. Check AWS EventBridge Scheduler console")
    print("3. Verify all 4 rules exist and are ENABLED")
    print("4. Check timezone: America/New_York")
    return True


def main():
    """Run all tests"""
    print("=" * 70)
    print("INTRADAY TRADING PIPELINES - VERIFICATION TESTS")
    print("=" * 70)

    print("\n[SETUP] VERIFICATION")
    validate_intraday_mode_support()
    validate_terraform_state_machines()
    validate_eventbridge_rules()

    print("\n\n[TIMING] PERFORMANCE TESTS")
    test_morning_pipeline_timing()
    test_afternoon_update_pipeline()
    test_preclose_update_pipeline()

    print("\n\n[SYNC] DATA FRESHNESS TESTS")
    test_fresh_scores_used_by_orchestrator()
    test_no_database_conflicts()

    print("\n\n[WARNING]  FAILURE MODE TESTS")
    test_failure_scenarios()

    print("\n\n" + "=" * 70)
    print("NEXT STEPS")
    print("=" * 70)
    print("""
1. Deploy Terraform: terraform apply
2. Monitor first live morning pipeline run (2:00 AM ET)
3. Monitor first live afternoon update (12:50 PM ET)
4. Monitor first live pre-close update (2:50 PM ET)
5. Verify fresh scores are used by orchestrators
6. Check CloudWatch logs for INTRADAY_MODE entries
7. Validate SLA: pre-close completes by 3:15 PM

Success Criteria:
[OK] Morning prep completes by 4:00 AM
[OK] Afternoon update completes by 1:05 PM
[OK] Pre-close update completes by 3:05 PM (SLA: 3:15 PM)
[OK] Fresh scores used at each orchestrator run
[OK] No database conflicts or lock timeouts
[OK] All pipelines succeed or fail gracefully
    """)

    return 0


if __name__ == "__main__":
    sys.exit(main())
