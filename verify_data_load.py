#!/usr/bin/env python3
"""
Data Load Verification Script
Verifies that all loaders have populated the database correctly
"""

import subprocess
import sys
from datetime import datetime

# ANSI colors
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

    print(f"{color}{symbol} {text}{RESET}")

def check_table_rows(table_name, min_rows=0):
    """Check if table has minimum rows"""
    try:
        result = subprocess.run(
            ['psql', '-U', 'stocks', '-h', 'localhost', 'stocks', '-tc',
             f"SELECT COUNT(*) FROM {table_name};"],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            print_status(f"{table_name}: Connection failed", 'ERROR')
            return False

        count = int(result.stdout.strip())

        if count >= min_rows:
            print_status(f"{table_name}: {count:,} rows ✓", 'SUCCESS')
            return True
        else:
            print_status(f"{table_name}: Only {count:,} rows (expected ≥{min_rows:,})", 'WARNING')
            return False

    except Exception as e:
        print_status(f"{table_name}: Error - {str(e)}", 'ERROR')
        return False

def main():
    """Run all verification checks"""

    print_header("DATA LOAD VERIFICATION")
    print_status(f"Starting verification at {datetime.now()}", 'INFO')

    # Track results
    checks = {}

    # 1. Portfolio Holdings
    print_header("1. Portfolio Holdings")
    checks['holdings'] = check_table_rows('portfolio_holdings', min_rows=1)

    # 2. Portfolio Performance History
    print_header("2. Portfolio Performance History")
    checks['performance'] = check_table_rows('portfolio_performance', min_rows=252)

    # 3. Daily Trading Signals
    print_header("3. Buy/Sell Signals")
    checks['signals_daily'] = check_table_rows('buy_sell_daily', min_rows=1000)
    checks['signals_daily_etf'] = check_table_rows('buy_sell_daily_etf', min_rows=1000)
    checks['signals_weekly'] = check_table_rows('buy_sell_weekly', min_rows=100)
    checks['signals_weekly_etf'] = check_table_rows('buy_sell_weekly_etf', min_rows=100)

    # 4. Stock Quality Scores
    print_header("4. Stock Quality Scores")
    checks['scores'] = check_table_rows('stock_scores', min_rows=100)

    # 5. Covered Call Opportunities
    print_header("5. Covered Call Opportunities")
    checks['covered_calls'] = check_table_rows('covered_call_opportunities', min_rows=1)

    # 6. Price Data
    print_header("6. Price Data")
    checks['prices'] = check_table_rows('latest_price_daily', min_rows=100)

    # Summary
    print_header("VERIFICATION SUMMARY")

    passed = sum(1 for v in checks.values() if v)
    total = len(checks)

    for check_name, passed_flag in checks.items():
        status = 'SUCCESS' if passed_flag else 'ERROR'
        symbol = '✅' if passed_flag else '❌'
        print(f"{symbol} {check_name:30} {'PASSED' if passed_flag else 'FAILED'}")

    print()
    if passed == total:
        print_status(f"✅ All {total} checks passed!", 'SUCCESS')
        print_status("✅ Database is ready for Portfolio Dashboard!", 'SUCCESS')
        print_status("✅ All loaders completed successfully!", 'SUCCESS')
        return 0
    else:
        failed = total - passed
        print_status(f"⚠️  {failed}/{total} checks failed", 'WARNING')
        print_status("⚠️  Some data may still be loading - check again in a few minutes", 'WARNING')
        return 1

if __name__ == "__main__":
    sys.exit(main())
