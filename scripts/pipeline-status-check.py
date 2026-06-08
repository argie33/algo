#!/usr/bin/env python3
"""
Pipeline Data Freshness Check

Monitors if all 8 critical tables have fresh data (<1 day old) with >=90% symbol coverage.
Used to verify Monday 2:00 AM ET morning prep pipeline completion.

Wraps monitor_freshness.py from temp directory with enhanced diagnostics.
"""

import os
import sys
import subprocess
from datetime import datetime, timedelta
import re

CRITICAL_TABLES = [
    'price_daily',
    'technical_data_daily',
    'buy_sell_daily',
    'signal_quality_scores',
    'swing_trader_scores',
    'market_health_daily',
    'trend_template_data',
    'sector_ranking'
]

def get_monitor_script():
    """Find the monitor freshness script."""
    temp_script = os.path.join(os.environ.get('TEMP', '/tmp'), 'monitor_freshness.py')
    if os.path.exists(temp_script):
        return temp_script

    # Try local scripts
    local_script = 'scripts/monitor_data_freshness.py'
    if os.path.exists(local_script):
        return local_script

    return None

def run_monitor():
    """Run the monitor freshness script and parse output."""
    script = get_monitor_script()
    if not script:
        print("[ERROR] Could not find monitor_freshness.py script")
        print("  - Expected in: $TEMP/monitor_freshness.py or scripts/monitor_data_freshness.py")
        return None

    try:
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.stdout + result.stderr
    except Exception as e:
        print(f"[ERROR] Failed to run monitor script: {e}")
        return None

def parse_monitor_output(output):
    """Parse monitor output to extract table status."""
    results = {}
    fresh_count = 0
    stale_count = 0
    error_count = 0

    lines = output.split('\n')
    in_table = False

    for line in lines:
        # Look for table status lines
        if any(table in line for table in CRITICAL_TABLES):
            parts = line.split()
            if len(parts) >= 2:
                table_name = parts[0]
                status = 'UNKNOWN'

                # Try to extract status
                if 'FRESH' in line:
                    status = 'FRESH'
                    fresh_count += 1
                elif 'STALE' in line:
                    status = 'STALE'
                    stale_count += 1
                elif 'ERROR' in line:
                    status = 'ERROR'
                    error_count += 1

                results[table_name] = {'status': status, 'line': line}

    return {
        'results': results,
        'fresh_count': fresh_count,
        'stale_count': stale_count,
        'error_count': error_count
    }

def main():
    print("="*90)
    print(f"PIPELINE DATA FRESHNESS CHECK - {datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print("="*90)
    print()

    # Run monitor script
    print("Checking pipeline table freshness...")
    monitor_output = run_monitor()

    if not monitor_output:
        print("[ERROR] Failed to retrieve freshness data")
        sys.exit(1)

    # Print raw output
    print(monitor_output)
    print()

    # Parse results
    parsed = parse_monitor_output(monitor_output)
    fresh = parsed['fresh_count']
    stale = parsed['stale_count']
    errors = parsed['error_count']
    total = len(CRITICAL_TABLES)

    print("="*90)

    # Determine status
    if fresh == total:
        print("[OK] SUCCESS: All 8 critical tables have fresh data with >=90% coverage")
        print("Pipeline status: READY FOR TRADING")
        exit_code = 0
    elif errors > 0:
        print(f"[ERROR] Pipeline status: STALE (0 FRESH, {stale} STALE, {errors} ERROR)")
        print()
        print("Action required:")
        print("  1. Check CloudWatch Logs for morning prep pipeline errors")
        print("  2. Verify ECS task status for stalled loaders")
        print("  3. Check RDS connection and slow queries")
        print("  4. Review loader-specific logs in CloudWatch")
        exit_code = 1
    else:
        print(f"[STALE] Pipeline status: INCOMPLETE (0 FRESH, {stale} STALE, {errors} ERROR)")
        print()
        print("Expected Monday 2:00 AM ET morning prep pipeline to complete. Tables still stale.")
        print()
        print("Check:")
        print("  1. Is morning prep Step Functions pipeline running?")
        print("  2. Check Step Functions execution history")
        print("  3. Review CloudWatch logs for loader failures")
        print("  4. Check if database is reachable")
        exit_code = 1

    print("="*90)
    sys.exit(exit_code)

if __name__ == '__main__':
    main()
