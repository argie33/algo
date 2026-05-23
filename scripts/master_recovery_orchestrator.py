#!/usr/bin/env python3
"""Master orchestrator for loader recovery."""

import subprocess
import sys
from datetime import datetime

def run_command(cmd, description):
    """Run a command and report results."""
    print(f"\n{'='*80}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {description}")
    print(f"{'='*80}")

    try:
        result = subprocess.run(cmd, shell=True, capture_output=False, text=True)
        return result.returncode == 0
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def main():
    print("\n" + "="*80)
    print("MASTER LOADER RECOVERY ORCHESTRATOR")
    print("="*80)

    # Step 1: Comprehensive audit
    print("\nSTEP 1: Comprehensive Audit")
    print("-" * 80)
    success = run_command(
        "python3 scripts/comprehensive_loader_audit.py",
        "Running comprehensive audit of all loaders..."
    )
    if not success:
        print("ERROR: Comprehensive audit failed")
        return 1

    # Step 2: Identify root causes
    print("\nSTEP 2: Root Cause Analysis")
    print("-" * 80)
    success = run_command(
        "python3 scripts/identify_failure_root_causes.py",
        "Analyzing failure patterns by category..."
    )
    if not success:
        print("WARNING: Root cause analysis had issues, but continuing...")

    # Step 3: Prepare recovery summary
    print("\nSTEP 3: Recovery Plan")
    print("-" * 80)
    print("""
Based on the audit and root cause analysis:

NEXT STEPS:
1. Review the failure categories above
2. For each category, apply targeted fixes:
   - Date/Time: Check date validation in affected loaders
   - API failures: Add retry logic or timeout increases
   - Resource: Increase memory/CPU in Terraform if needed
   - Other: Review specific loader code

3. After fixes are applied:
   python3 scripts/queue_all_loaders_systematically.py

4. Monitor execution:
   python3 scripts/final_completion_monitor.py

5. Validate completion:
   python3 scripts/comprehensive_loader_audit.py

REMEMBER:
- Some loaders may need Docker rebuild if code changed
- GitHub workflow handles Docker image build & push
- ECS task definitions auto-update after Terraform apply
""")

    print("\n" + "="*80)
    print("Recovery orchestration complete. Review above output and implement fixes.")
    print("="*80 + "\n")

    return 0

if __name__ == '__main__':
    sys.exit(main())
