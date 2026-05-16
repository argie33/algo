#!/usr/bin/env python3
"""Verify all Tier 1 and Tier 2 critical fixes are in place."""

import sys
import re

def check_file(filepath, pattern, description):
    """Check if a file contains a pattern."""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
            if re.search(pattern, content, re.MULTILINE | re.DOTALL):
                print(f"[OK] {description}")
                return True
            else:
                print(f"[FAIL] {description}")
                return False
    except Exception as e:
        print(f"[FAIL] {description} (Error: {e})")
        return False

def main():
    """Run all verifications."""
    print("=" * 70)
    print("TIER 1 & 2 CRITICAL FIX VERIFICATION")
    print("=" * 70)

    results = []

    # Tier 1 fixes
    print("\nTIER 1: CRASH-LEVEL BUGS")
    print("-" * 70)

    # 1.1: Missing import json in swing_score
    results.append(check_file(
        'algo_swing_score.py',
        r'^import json',
        "1.1 algo_swing_score.py imports json"
    ))

    # 1.2: check_duplicate_order_hard uses side parameter
    results.append(check_file(
        'algo_pretrade_checks.py',
        r"entry_reason LIKE %s.*\%\{side\}\%",
        "1.2 check_duplicate_order_hard() uses side parameter in SQL"
    ))

    # 1.3: Pyramid adds run PreTradeChecks
    results.append(check_file(
        'algo_pyramid.py',
        r'from algo_pretrade_checks import PreTradeChecks',
        "1.3 algo_pyramid.py imports PreTradeChecks"
    ))

    results.append(check_file(
        'algo_pyramid.py',
        r'pretrade_checks\.run_all\(',
        "1.3 execute_add() calls PreTradeChecks.run_all()"
    ))

    # 1.4: Paper mode gates NameError fix
    results.append(check_file(
        'algo_paper_mode_gates.py',
        r'gates_dict = \{',
        "1.4 algo_paper_mode_gates.py creates gates_dict before using it"
    ))

    # 1.5: Paper mode gates date comparisons
    results.append(check_file(
        'algo_paper_mode_gates.py',
        r"WHERE report_date <= %s",
        "1.5 Paper mode gates use <= operator (not >=)"
    ))

    print("\nTIER 2: SCHEMA MISMATCHES")
    print("-" * 70)

    # 2.1: trend_template_daily -> trend_template_data
    results.append(check_file(
        'lambda/api/lambda_function.py',
        r'FROM trend_template_data',
        "2.1 Lambda API uses trend_template_data (not trend_template_daily)"
    ))

    # 2.2: etf_symbols fix
    results.append(check_file(
        'lambda/api/lambda_function.py',
        r'LEFT JOIN company_profile',
        "2.2 Lambda API joins company_profile for ETF symbols"
    ))

    # 2.3: market_sentiment -> fear_greed_index
    results.append(check_file(
        'lambda/api/lambda_function.py',
        r'FROM fear_greed_index',
        "2.3 Lambda API uses fear_greed_index (not market_sentiment)"
    ))

    # 2.4: backtest_runs table exists
    results.append(check_file(
        'init_database.py',
        r'CREATE TABLE.*backtest_runs',
        "2.4 init_database.py defines backtest_runs table"
    ))

    # 2.5: key_metrics error handling
    results.append(check_file(
        'lambda/api/lambda_function.py',
        r'if not row:\s+return json_response\(200, \{\}\)',
        "2.5 Lambda API handles empty key_metrics gracefully"
    ))

    print("\n" + "=" * 70)
    passed = sum(results)
    total = len(results)
    print(f"RESULTS: {passed}/{total} checks passed")
    print("=" * 70)

    if passed == total:
        print("[SUCCESS] ALL CRITICAL FIXES VERIFIED")
        return 0
    else:
        print(f"[FAILED] {total - passed} issues found")
        return 1

if __name__ == '__main__':
    sys.exit(main())
