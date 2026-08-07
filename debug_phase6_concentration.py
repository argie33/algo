#!/usr/bin/env python3
"""
Diagnostic script to test Phase 6 concentration calculations.
This script will:
1. Check current database state
2. Test concentration calculations with sample data
3. Identify any bugs in the formula
"""

import sys
import os
from datetime import datetime, date

os.environ['DB_NAME'] = 'stocks'

# Add the repo to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from decimal import Decimal

def test_concentration_calc():
    """Test Phase 6 concentration calculation logic"""

    print("\n" + "="*80)
    print("PHASE 6 CONCENTRATION DIAGNOSTIC")
    print("="*80)

    # Test Case 1: Portfolio with multiple positions
    print("\nTest Case 1: Current Market State")
    print("-" * 80)

    portfolio_value = Decimal('71592.31')
    positions = [
        {'symbol': 'MSFT', 'value': Decimal('3998.88')},
        {'symbol': 'DAC', 'value': Decimal('2433.55')},
        {'symbol': 'EAT', 'value': Decimal('4090.86')},
        {'symbol': 'MCK', 'value': Decimal('1742.76')},
        {'symbol': 'ECPG', 'value': Decimal('1957.60')},
    ]

    print(f"Portfolio value: ${float(portfolio_value):,.2f}")
    print(f"Max position size: 6.0%")
    print(f"Number of positions: {len(positions)}\n")

    print(f"{'Symbol':<10} {'Value':<15} {'% of Portfolio':<20} {'Status':<10}")
    print("-" * 55)

    total_position_value = Decimal('0')
    violations = 0

    for pos in positions:
        pct = (pos['value'] / portfolio_value * Decimal('100'))
        pct_float = float(pct)
        total_position_value += pos['value']

        status = "PASS" if pct_float <= 6.0 else "FAIL"
        if pct_float > 6.0:
            violations += 1

        print(f"{pos['symbol']:<10} ${float(pos['value']):>13,.2f} {pct_float:>18.2f}% {status:<10}")

    print("-" * 55)
    total_pct = total_position_value / portfolio_value * Decimal('100')
    print(f"{'TOTAL':<10} ${float(total_position_value):>13,.2f} {float(total_pct):>18.2f}%")
    print(f"\n📊 Violations: {violations}")
    print(f"✅ All positions should pass (< 6% limit)" if violations == 0 else f"❌ {violations} positions exceed 6% limit")

    # Test Case 2: What if denominator was wrong?
    print("\n\nTest Case 2: Simulated Wrong Denominator ($25k)")
    print("-" * 80)

    wrong_denominator = Decimal('25000')
    print(f"Wrong denominator: ${float(wrong_denominator):,.2f}")
    print(f"\n{'Symbol':<10} {'Value':<15} {'% of $25k':<20} {'Status':<10}")
    print("-" * 55)

    violations_wrong = 0
    for pos in positions:
        pct_wrong = (pos['value'] / wrong_denominator * Decimal('100'))
        pct_wrong_float = float(pct_wrong)

        status = "PASS" if pct_wrong_float <= 6.0 else "FAIL"
        if pct_wrong_float > 6.0:
            violations_wrong += 1

        print(f"{pos['symbol']:<10} ${float(pos['value']):>13,.2f} {pct_wrong_float:>18.2f}% {status:<10}")

    print("-" * 55)
    total_pct_wrong = total_position_value / wrong_denominator * Decimal('100')
    print(f"{'TOTAL':<10} ${float(total_position_value):>13,.2f} {float(total_pct_wrong):>18.2f}%")
    print(f"\n🔴 Violations with wrong denominator: {violations_wrong}")
    if violations_wrong > 0:
        print(f"⚠️  This would cause {violations_wrong} FALSE force-exits!")

    # Test Case 3: Test of invested capital denominator
    print("\n\nTest Case 3: Invested Capital Denominator (SUM of positions)")
    print("-" * 80)

    invested_capital = total_position_value
    print(f"Invested capital: ${float(invested_capital):,.2f}")
    print(f"Cash available: ${float(portfolio_value - invested_capital):,.2f}")
    print(f"Utilization: {float(invested_capital/portfolio_value)*100:.1f}%\n")

    print(f"{'Symbol':<10} {'Value':<15} {'% of Invested':<20} {'Status':<10}")
    print("-" * 55)

    violations_invested = 0
    for pos in positions:
        pct_invested = (pos['value'] / invested_capital * Decimal('100'))
        pct_invested_float = float(pct_invested)

        status = "PASS" if pct_invested_float <= 6.0 else "FAIL"
        if pct_invested_float > 6.0:
            violations_invested += 1

        print(f"{pos['symbol']:<10} ${float(pos['value']):>13,.2f} {pct_invested_float:>18.2f}% {status:<10}")

    print("-" * 55)
    invested_total_pct = total_position_value / invested_capital * Decimal('100')
    print(f"{'TOTAL':<10} ${float(total_position_value):>13,.2f} {float(invested_total_pct):>18.2f}%")
    print(f"\n📊 Violations: {violations_invested}")
    if violations_invested > 0:
        print(f"🔴 Using invested capital denominator causes {violations_invested} violations")

    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Correct denominator (portfolio value ${float(portfolio_value):,.2f}): {violations} violations")
    print(f"Wrong denominator ($25k): {violations_wrong} violations  {'❌ BUG!' if violations_wrong > 0 else ''}")
    print(f"Invested capital denominator: {violations_invested} violations  {'❌ Alternative!' if violations_invested > 0 else ''}")

    if violations_wrong > 0:
        print(f"\n🚨 Phase 6 is likely using the WRONG denominator if it force-exits any positions!")


if __name__ == '__main__':
    test_concentration_calc()
