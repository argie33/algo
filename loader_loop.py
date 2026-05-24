#!/usr/bin/env python3
"""Comprehensive loader test suite - verifies all 24 loaders."""
import os
import sys
from datetime import datetime
from pathlib import Path

# Set credentials
os.environ['SEC_USER_AGENT'] = 'algo-trading argeropolos@gmail.com'

LOADERS = [
    'load_stock_prices_daily',
    'load_stock_prices_weekly',
    'load_technical_data_daily',
    'load_algo_metrics_daily',
    'load_company_profile',
    'load_earnings_calendar',
    'load_industry_ranking',
    'load_market_health_daily',
    'load_fear_greed_index',
    'load_weight_optimization',
    'load_naaim',
    'load_signals_daily',
    'load_growth_metrics',
    'load_quality_metrics',
    'load_aaii_sentiment',
    'load_analyst_sentiment_analysis',
    'load_analyst_upgrade_downgrade',
    'load_value_metrics',
    'load_signal_quality_scores',
    'load_swing_trader_scores',
    'load_balance_sheet',
    'load_cash_flow',
    'load_income_statement',
    'load_trend_criteria_data',
]

def test_loader_import(loader_name):
    """Test if loader can be imported."""
    try:
        __import__(f'loaders.{loader_name}')
        return True, None
    except Exception as e:
        return False, str(e)[:100]

def main():
    start_time = datetime.now()
    results_file = 'loader_loop_results.txt'
    
    output_lines = [
        f"LOADER TEST SUITE - {start_time.strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 70,
        f"Testing {len(LOADERS)} loaders...",
        "",
    ]
    
    passed = []
    failed = []
    
    for i, loader in enumerate(LOADERS, 1):
        success, error = test_loader_import(loader)
        status = "PASS" if success else "FAIL"
        
        output_lines.append(f"{i:2d}. {loader:40} [{status}]")
        
        if success:
            passed.append(loader)
        else:
            failed.append((loader, error))
    
    # Summary
    output_lines.extend([
        "",
        "=" * 70,
        f"SUMMARY",
        f"PASSED: {len(passed)}/24",
        f"FAILED: {len(failed)}/24",
        "",
    ])
    
    if failed:
        output_lines.append("FAILED LOADERS:")
        for loader, error in failed:
            output_lines.append(f"  {loader}")
            if error:
                output_lines.append(f"    Error: {error}")
    else:
        output_lines.append("ALL LOADERS PASSED!")
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    output_lines.extend([
        "",
        f"Duration: {duration:.2f}s",
        f"Completion: {end_time.strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 70,
    ])
    
    # Write results
    output = "\n".join(output_lines)
    with open(results_file, 'w') as f:
        f.write(output)
    
    # Print and return
    print(output)
    return 0 if len(failed) == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
