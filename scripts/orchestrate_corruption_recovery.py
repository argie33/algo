#!/usr/bin/env python3
"""Master orchestration for full corruption recovery pipeline.

This script manages the complete recovery process:
1. Audit current corruptions
2. Execute comprehensive reload
3. Execute targeted severe/moderate reload
4. Validate restoration
5. Generate final report
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def run_command(cmd, description, cwd=None):
    """Run a command and return success status."""
    print(f"\n{'=' * 80}")
    print(f"[{datetime.now().isoformat()}] {description}")
    print(f"{'=' * 80}")

    try:
        result = subprocess.run(cmd, shell=True, cwd=cwd or str(REPO_ROOT), capture_output=True, text=True)
        if result.returncode == 0:
            print("[OK] Success")
            if result.stdout:
                print(result.stdout[:500])
            return True
        else:
            print(f"[FAILED] Exit code {result.returncode}")
            if result.stderr:
                print(f"Error: {result.stderr[:500]}")
            return False
    except Exception as e:
        print(f"[ERROR] Exception: {e}")
        return False


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phases",
        default="1,2,3,4,5",
        help="Phases to run (comma-separated: 1=audit, 2=comprehensive, 3=targeted, 4=validate, 5=report)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without executing")
    args = parser.parse_args()

    phases = [int(p) for p in args.phases.split(",")]

    print("\n" + "=" * 80)
    print("CORRUPTION RECOVERY ORCHESTRATION")
    print("=" * 80)
    print(f"Phases to execute: {', '.join(map(str, phases))}")
    print(f"Dry-run: {args.dry_run}")
    print()

    results = {"start_time": datetime.now().isoformat(), "phases": {}}

    # Phase 1: Audit
    if 1 in phases:
        cmd = "python scripts/audit_corruption_damage.py"
        success = run_command(cmd, "PHASE 1: Audit current corruptions", cwd=str(REPO_ROOT))
        results["phases"][1] = {"status": "complete" if success else "failed", "description": "Audit"}

        if success:
            try:
                with open("/tmp/corruption_audit.json") as f:
                    audit = json.load(f)
                    results["phases"][1]["records_corrupted"] = len(audit)
            except (OSError, json.JSONDecodeError):
                pass

    # Phase 2: Comprehensive Reload
    if 2 in phases:
        if args.dry_run:
            cmd = "python scripts/comprehensive_corruption_recovery.py --dry-run"
            run_command(cmd, "PHASE 2: Preview comprehensive reload")
        else:
            cmd = "python scripts/comprehensive_corruption_recovery.py --fix"
            success = run_command(cmd, "PHASE 2: Execute comprehensive reload")
            results["phases"][2] = {
                "status": "complete" if success else "failed",
                "description": "Comprehensive reload",
            }

    # Phase 3: Targeted Severe/Moderate Reload
    if 3 in phases:
        if args.dry_run:
            cmd = "python scripts/full_history_reload_corrupted.py --dry-run"
            run_command(cmd, "PHASE 3: Preview targeted severe/moderate reload")
        else:
            cmd = "python scripts/full_history_reload_corrupted.py --fix"
            success = run_command(cmd, "PHASE 3: Execute targeted severe/moderate reload")
            results["phases"][3] = {"status": "complete" if success else "failed", "description": "Targeted reload"}

    # Phase 4: Validate
    if 4 in phases:
        cmd = "python scripts/audit_corruption_damage.py"
        success = run_command(cmd, "PHASE 4: Validate restoration")
        results["phases"][4] = {"status": "complete" if success else "failed", "description": "Validation audit"}

        if success:
            try:
                with open("/tmp/corruption_audit.json") as f:
                    audit = json.load(f)
                    results["phases"][4]["records_remaining"] = len(audit)
                    results["phases"][4]["records_restored"] = results["phases"].get(1, {}).get(
                        "records_corrupted", 0
                    ) - len(audit)
            except (OSError, json.JSONDecodeError):
                pass

    # Phase 5: Generate Report
    if 5 in phases:
        cmd = "python scripts/generate_divergence_recovery_report.py"
        success = run_command(cmd, "PHASE 5: Generate divergence recovery report")
        results["phases"][5] = {"status": "complete" if success else "failed", "description": "Final report"}

    # Summary
    print("\n" + "=" * 80)
    print("RECOVERY ORCHESTRATION COMPLETE")
    print("=" * 80)
    print()

    for phase_id in sorted(results["phases"].keys()):
        phase = results["phases"][phase_id]
        status = phase.get("status", "skipped")
        desc = phase.get("description", "")
        print(f"Phase {phase_id}: {desc:40} [{status}]")
        if "records_corrupted" in phase:
            print(f"           Corrupted: {phase['records_corrupted']}")
        if "records_remaining" in phase:
            print(f"           Remaining: {phase['records_remaining']}")
        if "records_restored" in phase:
            print(f"           Restored: {phase['records_restored']}")

    print()
    print("NEXT STEPS:")
    print("1. Review outputs in /tmp/corruption_audit.json")
    print("2. Review outputs in /tmp/divergence_report.json")
    print("3. Run validate_yfinance_plausibility.py to flag garbage values")
    print("4. Commit recovery scripts and prevention rules")
    print("5. Update MEMORY.md with lessons learned")

    results["end_time"] = datetime.now().isoformat()

    # Save results
    report_file = "/tmp/recovery_orchestration_results.json"
    with open(report_file, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nOrchestration results saved to: {report_file}")


if __name__ == "__main__":
    main()
