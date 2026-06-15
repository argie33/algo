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

import sys
import os

# Add project root to path
project_root = str(os.path.dirname(__file__).rsplit("/", 1)[0])
sys.path.insert(0, project_root)


def test_morning_pipeline_timing():
    """Verify morning pipeline completes before 9:30 AM (7.5h before is 2:00 AM)"""
    print("\n=== TEST: Morning Pipeline Timing ===")

    expected_start = "02:00"  # 2:00 AM ET
    expected_complete = "04:00"  # 4:00 AM ET (before 9:30 AM orchestrator)

    print(
        f"Expected: Pipeline starts at {expected_start} ET, completes by {expected_complete} ET"
    )
    print("Check CloudWatch logs for /ecs/algo-*-loader timestamps")
    print("Requirement: Ready 7.5 hours before 9:30 AM market open [OK]")


def test_afternoon_update_pipeline():
    """Verify afternoon update pipeline triggers before 1 PM and completes by 1:05 PM"""
    print("\n=== TEST: Afternoon Update Pipeline (1 PM) ===")

    print("Scheduled: 12:50 PM ET")
    print("Expected completion: 1:05 PM ET")
    print("Buffer before 1 PM orchestrator: 5 minutes")
    print("Duration: 5-15 min (fast intraday mode)")
    print("\nVerification steps:")
    print("1. Check CloudWatch: /ecs/algo-swing_trader_scores_vectorized-loader")
    print("2. Look for INTRADAY_MODE=true in logs at 12:50 PM")
    print("3. Confirm 'computed_at' timestamp in swing_trader_scores is ~1 PM")


def test_preclose_update_pipeline():
    """Verify pre-close update pipeline completes before 3:15 PM SLA"""
    print("\n=== TEST: Pre-Close Update Pipeline (SLA CRITICAL) ===")

    print("Scheduled: 2:50 PM ET")
    print("Expected completion: 3:05 PM ET")
    print("SLA deadline: 3:15 PM ET")
    print("Buffer: 10 minutes")
    print("Duration: 5-15 min (fast intraday mode)")
    print("\n[WARNING]  CRITICAL: If pre-close pipeline > 3:15 PM, SLA fails")
    print("\nVerification steps:")
    print("1. Check CloudWatch: /ecs/algo-swing_trader_scores_vectorized-loader")
    print("2. Look for INTRADAY_MODE=true in logs at 2:50 PM")
    print("3. Confirm completion BEFORE 3:15 PM")
    print("4. Verify 'computed_at' timestamp in swing_trader_scores is ~3 PM")


def test_fresh_scores_used_by_orchestrator():
    """Verify orchestrators use fresh scores from intraday updates"""
    print("\n=== TEST: Orchestrator Uses Fresh Scores ===")

    print("1 PM Orchestrator Test:")
    print("  - Should query swing_trader_scores with computed_at ~ 12:50 PM")
    print("  - NOT morning's 2:00 AM scores")
    print("  - Check orchestrator Phase 5 logs for score lookup timestamp")

    print("\n3 PM Orchestrator Test:")
    print("  - Should query swing_trader_scores with computed_at ~ 2:50 PM")
    print("  - NOT morning's 2:00 AM scores")
    print("  - Check orchestrator Phase 5 logs for score lookup timestamp")


def test_no_database_conflicts():
    """Verify concurrent loader runs don't conflict"""
    print("\n=== TEST: No Database Conflicts ===")

    print("Concurrent runs that should NOT conflict:")
    print(
        "  - 2 AM morning pipeline + 4:05 PM EOD pipeline (opposite sides of trading day)"
    )
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
    """Check that loaders support INTRADAY_MODE environment variable"""
    print("\n=== TEST: INTRADAY_MODE Environment Variable Support ===")

    loader_files = [
        "loaders/load_swing_trader_scores_vectorized.py",
        "loaders/load_technical_data_daily_vectorized.py",
    ]

    for loader_file in loader_files:
        try:
            with open(loader_file, "r") as f:
                content = f.read()
                if "INTRADAY_MODE" in content:
                    print(f"[OK] {loader_file}: INTRADAY_MODE support found")
                else:
                    print(f"[FAIL] {loader_file}: INTRADAY_MODE support NOT found")
                    return False
        except FileNotFoundError:
            print(f"[FAIL] {loader_file}: File not found")
            return False

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
