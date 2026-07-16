#!/usr/bin/env python3
"""
Trigger morning, EOD, and computed metrics data pipelines in sequence.
For use as a workaround when EventBridge Scheduler is not deployed.

Pipeline execution order:
1. Morning (2:00 AM ET): Loads prices + technicals
2. EOD (4:05 PM ET): Loads signals + financial data
3. Computed Metrics (7:00 PM ET): Loads value/quality/growth/stability + scores

Use as: python scripts/trigger_data_pipelines_all.py
"""

import subprocess
import time
import sys


def trigger_pipeline(script_name: str, description: str) -> bool:
    """Trigger a pipeline and return success status."""
    print(f"\n[INFO] Triggering {description}...")
    result = subprocess.run([sys.executable, f"scripts/{script_name}"], capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(f"[ERROR] {description} failed: {result.stderr}")
        return False
    return True


if __name__ == "__main__":
    print("=" * 80)
    print("TRIGGERING ALL DATA PIPELINES (MORNING → EOD → COMPUTED METRICS)")
    print("=" * 80)

    success = True

    # Step 1: Morning pipeline (prices + technicals)
    if trigger_pipeline("trigger_morning_pipeline.py", "morning pipeline"):
        print("\n[WAIT] Morning pipeline executing (waiting 60 seconds)...")
        time.sleep(60)

        # Step 2: EOD pipeline (signals + financial data)
        if trigger_pipeline("trigger_eod_pipeline.py", "EOD pipeline"):
            print("\n[WAIT] EOD pipeline executing (waiting 60 seconds)...")
            time.sleep(60)

            # Step 3: Computed metrics pipeline (value/quality/growth/stability/scores)
            if not trigger_pipeline("trigger_computed_metrics_pipeline.py", "computed metrics pipeline"):
                success = False
        else:
            success = False
    else:
        success = False

    if success:
        print("\n" + "=" * 80)
        print("[SUCCESS] All pipelines triggered successfully!")
        print("=" * 80)
    else:
        print("\n" + "=" * 80)
        print("[FAIL] One or more pipelines failed")
        print("=" * 80)

    sys.exit(0 if success else 1)
