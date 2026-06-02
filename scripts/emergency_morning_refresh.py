#!/usr/bin/env python3
"""Emergency: manually refresh morning data for orchestrator run.

Run this when the automatic morning pipeline fails.
"""

import sys
import subprocess
from datetime import date
import time

LOADERS = [
    ('stock_prices_daily', {'LOADER_INTERVALS': '1d', 'LOADER_ASSET_CLASSES': 'stock'}),
    ('technical_data_daily', {}),
    ('buy_sell_daily', {}),
    ('signal_quality_scores', {}),
    ('swing_trader_scores', {}),
]

def run_loader(loader_name, env_overrides):
    """Run a single loader."""
    print(f'\n{"="*60}')
    print(f'[{time.strftime("%H:%M:%S")}] Running: {loader_name}')
    print(f'{"="*60}')

    cmd = f'python loaders/load_{loader_name.split("_")[0]}_{loader_name.split("_")[1]}_*.py'

    # Try to find the right file
    import glob
    pattern = f'loaders/load_*{loader_name.replace("_", "*")}*.py'
    files = glob.glob(pattern)

    if not files:
        print(f'ERROR: Could not find loader script for {loader_name}')
        return False

    loader_script = files[0]
    print(f'Found: {loader_script}')

    # Build command with env overrides
    import os
    env = os.environ.copy()
    for key, value in env_overrides.items():
        env[key] = value

    try:
        result = subprocess.run(
            ['python', loader_script, '--parallelism', '2'],
            env=env,
            timeout=600,
            capture_output=False
        )
        if result.returncode == 0:
            print(f'✓ {loader_name} completed')
            return True
        else:
            print(f'✗ {loader_name} failed (code {result.returncode})')
            return False
    except subprocess.TimeoutExpired:
        print(f'✗ {loader_name} timed out (>10min)')
        return False
    except Exception as e:
        print(f'✗ {loader_name} error: {e}')
        return False

def main():
    print(f'\n[EMERGENCY] Morning data refresh - starting at {time.strftime("%H:%M:%S")}')
    print(f'Orchestrator runs at 9:30 AM ET (~{9*60+30 - int(time.time()) // 60} minutes away)')

    success_count = 0
    for loader_name, env_overrides in LOADERS:
        if run_loader(loader_name, env_overrides):
            success_count += 1
            time.sleep(5)  # Brief pause between loaders
        else:
            print(f'WARNING: {loader_name} failed, continuing...')

    print(f'\n{"="*60}')
    print(f'Summary: {success_count}/{len(LOADERS)} loaders completed')
    print(f'Completed at: {time.strftime("%H:%M:%S")}')

    if success_count == len(LOADERS):
        print('✓ All data refreshed - orchestrator run should succeed')
        return 0
    else:
        print(f'✗ {len(LOADERS) - success_count} loaders failed - data may be incomplete')
        return 1

if __name__ == '__main__':
    sys.exit(main())
