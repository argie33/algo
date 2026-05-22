#!/usr/bin/env python3
"""
Continuous loader completion monitor - runs until all loaders are verified complete.
Checks every 60 seconds and reports progress.
"""
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

def check_status():
    """Run the status checker and return parsed results."""
    result = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "check_ecs_loader_completion.py")],
        capture_output=True,
        text=True,
        timeout=30
    )

    lines = result.stdout.split('\n')

    done_count = 0
    run_count = 0
    failed_count = 0
    unknown_count = 0

    for line in lines:
        if '[DONE]' in line:
            done_count += 1
        elif '[RUN ]' in line:
            run_count += 1
        elif '[FAIL]' in line:
            failed_count += 1
        elif '[????]' in line:
            unknown_count += 1

    # Extract summary line
    for line in lines:
        if 'Summary from' in line:
            return {
                'done': done_count,
                'running': run_count,
                'failed': failed_count,
                'unknown': unknown_count,
                'timestamp': datetime.now(),
                'summary_line': line,
                'full_output': result.stdout
            }

    return {
        'done': done_count,
        'running': run_count,
        'failed': failed_count,
        'unknown': unknown_count,
        'timestamp': datetime.now(),
        'full_output': result.stdout
    }

def main():
    print("=" * 80)
    print("LOADER COMPLETION MONITOR")
    print("=" * 80)
    print(f"Started: {datetime.now().isoformat()}")
    print("Checking every 60 seconds until all loaders complete...")
    print()

    previous_done = 0
    check_count = 0
    max_checks = 120  # ~2 hours of monitoring

    while check_count < max_checks:
        check_count += 1

        try:
            status = check_status()
            done = status['done']
            running = status['running']
            failed = status['failed']
            unknown = status['unknown']
            total_visible = done + running + failed + unknown

            # Report progress
            progress = f"[{check_count:3}/120] {datetime.now().isoformat()} | DONE: {done:2} | RUN: {running:2} | FAILED: {failed:2} | UNKNOWN: {unknown:2}"

            if done > previous_done:
                print(f"✓ {progress} [NEW COMPLETIONS!]")
                previous_done = done
            else:
                print(f"  {progress}")

            # Check for completion
            if unknown == 0 and running == 0 and failed == 0:
                print()
                print("=" * 80)
                print(f"SUCCESS: All {done} loaders have completed!")
                print(f"Completed at: {datetime.now().isoformat()}")
                print("=" * 80)
                return 0

            # Wait before next check (unless this is the last check)
            if check_count < max_checks:
                time.sleep(60)

        except KeyboardInterrupt:
            print("\nMonitoring stopped by user")
            return 1
        except Exception as e:
            print(f"ERROR during check {check_count}: {e}")
            time.sleep(60)

    print()
    print("=" * 80)
    print("Monitoring timeout - not all loaders completed within 2 hours")
    print("Run check_ecs_loader_completion.py for current status")
    print("=" * 80)
    return 1

if __name__ == '__main__':
    sys.exit(main())
