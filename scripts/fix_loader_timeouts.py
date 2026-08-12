#!/usr/bin/env python3
"""Fix loader timeouts in local_loader_scheduler.py based on root cause analysis.

SESSION 92+ FIXES:
- analyst_sentiment: 30 min -> 45 min (yfinance rate limiting)
- analyst_earnings_estimates: 30 min -> 45 min (yfinance rate limiting)
- analyst_upgrades: 40 min -> 45 min (consistency)
- valuations: 45 min -> 60 min (SEC API rate limiting)
- sec_valuations: 45 min -> 60 min (was failing at 45m)
- segment_info: 45 min -> 60 min (SEC API rate limiting)
- insider_holdings: 30 min -> 45 min (SEC bulk download + rate limiting)
- insider_velocity: 30 min -> 45 min (cascade dependency)
- dividends: 30 min -> 40 min (yfinance rate limiting)
- earnings_calendar: 45 min -> 60 min (was failing at 45m)
"""

import re

def fix_timeouts():
    with open('scripts/local_loader_scheduler.py', 'r') as f:
        content = f.read()

    # Define timeout updates
    updates = {
        '"analyst_sentiment": 30 * 60,': '"analyst_sentiment": 45 * 60,',
        '"analyst_earnings_estimates": 30\n        * 60,': '"analyst_earnings_estimates": 45\n        * 60,',
        '"analyst_upgrades": 40 * 60,': '"analyst_upgrades": 45 * 60,',
        '"valuations": 45 * 60,': '"valuations": 60 * 60,',
        '"sec_valuations": 45 * 60,': '"sec_valuations": 60 * 60,',
        '"segment_info": 45 * 60,': '"segment_info": 60 * 60,',
        '"insider_holdings": 30 * 60,': '"insider_holdings": 45 * 60,',
        '"insider_velocity": 30 * 60,': '"insider_velocity": 45 * 60,',
        '"dividends": 30 * 60,': '"dividends": 40 * 60,',
        '"earnings_calendar": 45\n        * 60,': '"earnings_calendar": 60\n        * 60,',
    }

    modified = content
    for old, new in updates.items():
        if old in modified:
            modified = modified.replace(old, new)
            print(f"[OK] Updated: {old[:40]}")
        else:
            print(f"[SKIP] NOT FOUND: {old[:40]}")

    # Write back
    with open('scripts/local_loader_scheduler.py', 'w') as f:
        f.write(modified)

    print("\nTimeout updates complete!")

    # Show changes
    import subprocess
    try:
        result = subprocess.run(['git', 'diff', 'scripts/local_loader_scheduler.py'],
                              capture_output=True, text=True, timeout=5)
        if result.stdout:
            lines = result.stdout.split('\n')[:50]
            print("\nGit diff (first 50 lines):")
            for line in lines:
                print(line)
    except Exception as e:
        print(f"Could not run git diff: {e}")

if __name__ == "__main__":
    fix_timeouts()
