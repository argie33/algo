#!/usr/bin/env python3
"""
Master Data Loader Script - Runs ALL essential loaders in correct order
Populates portfolio dashboard with REAL DATA from all sources
"""

import subprocess
import sys
import time
from datetime import datetime

# ANSI colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_header(text):
    """Print section header"""
    print(f"\n{BLUE}{'='*70}{RESET}")
    print(f"{BLUE}{text:^70}{RESET}")
    print(f"{BLUE}{'='*70}{RESET}\n")

def print_status(text, status='INFO'):
    """Print status message"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    if status == 'SUCCESS':
        color = GREEN
        symbol = '✅'
    elif status == 'ERROR':
        color = RED
        symbol = '❌'
    elif status == 'WARNING':
        color = YELLOW
        symbol = '⚠️'
    else:
        color = BLUE
        symbol = 'ℹ️'

    print(f"{color}{symbol} [{timestamp}] {text}{RESET}")

def run_loader(script_name, description):
    """Run a single loader script"""
    print_status(f"Starting: {description}...", 'INFO')

    try:
        result = subprocess.run(
            [sys.executable, script_name],
            cwd='/home/stocks/algo',
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout per loader
        )

        if result.returncode == 0:
            print_status(f"✅ {description} completed successfully", 'SUCCESS')
            return True
        else:
            print_status(f"❌ {description} failed with code {result.returncode}", 'ERROR')
            if result.stderr:
                print(f"   Error: {result.stderr[:200]}")
            return False
    except subprocess.TimeoutExpired:
        print_status(f"❌ {description} timed out after 10 minutes", 'ERROR')
        return False
    except Exception as e:
        print_status(f"❌ {description} exception: {str(e)}", 'ERROR')
        return False

def main():
    """Run all data loaders in correct order"""

    print_header("MASTER DATA LOADER - PORTFOLIO DASHBOARD")
    print_status(f"Starting comprehensive data load at {datetime.now()}", 'INFO')

    # List of loaders in order of dependency
    loaders = [
        # Phase 1: Real-time Alpaca portfolio data
        ("loadalpacaportfolio.py", "Portfolio Holdings (Alpaca Real-Time)"),

        # Phase 2: Price data and technical indicators
        ("loadlatestpricedaily.py", "Latest Daily Prices"),
        ("loaddailycompanydata.py", "Company Data & Sector Classification"),

        # Phase 3: Quality scores and fundamental data
        ("loadstockscores.py", "Stock Quality Scores (7-Factor Model)"),
        ("loadearningshistory.py", "Earnings History & Growth Metrics"),

        # Phase 4: Trading signals
        ("loadbuyselldaily.py", "Buy/Sell Daily Signals"),
        ("loadbuysell_etf_daily.py", "Buy/Sell Daily Signals (ETFs)"),

        # Phase 5: Options and hedging
        ("loadcoveredcallopportunities.py", "Covered Call Opportunities"),

        # Phase 6: Market context
        ("loadmarket.py", "Market Indices & Correlation Data"),
        ("loadsentiment.py", "Market Sentiment"),
    ]

    results = {}
    start_time = time.time()

    print_status(f"Running {len(loaders)} data loaders", 'INFO')
    print("Loaders to execute:")
    for i, (script, desc) in enumerate(loaders, 1):
        print(f"  {i:2d}. {desc}")
    print()

    for script, description in loaders:
        success = run_loader(script, description)
        results[description] = success
        time.sleep(1)  # Small delay between loaders

    # Print summary
    print_header("DATA LOAD SUMMARY")

    successful = sum(1 for v in results.values() if v)
    total = len(results)

    for description, success in results.items():
        status = 'SUCCESS' if success else 'ERROR'
        symbol = '✅' if success else '❌'
        print(f"{symbol} {description:50} {'PASSED' if success else 'FAILED'}")

    print()
    print_status(f"Completed: {successful}/{total} loaders successful", 'SUCCESS' if successful == total else 'WARNING')

    elapsed_time = time.time() - start_time
    hours, remainder = divmod(int(elapsed_time), 3600)
    minutes, seconds = divmod(remainder, 60)

    print_status(f"Total time: {hours}h {minutes}m {seconds}s", 'INFO')

    # Exit status
    if successful == total:
        print_status("✅ All data loaders completed successfully!", 'SUCCESS')
        print_status("Portfolio Dashboard should now show REAL DATA with no synthetic values", 'SUCCESS')
        return 0
    else:
        failed = total - successful
        print_status(f"❌ {failed} loader(s) failed - see above for details", 'ERROR')
        print_status("Run failed loaders individually to debug issues", 'ERROR')
        return 1

if __name__ == "__main__":
    sys.exit(main())
