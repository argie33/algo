#!/usr/bin/env python3
"""Identify root causes of loader failures by analyzing logs."""

import boto3
import json
from datetime import datetime, timedelta
from collections import defaultdict

logs = boto3.client('logs', region_name='us-east-1')

# Loaders that were failing according to audit
FAILING_LOADERS = [
    "aaiidata", "algo_metrics_daily", "analyst_sentiment", "company_profile",
    "earnings_calendar", "earnings_history", "earnings_sp500", "earnings_surprise",
    "econ_data", "eod_bulk_refresh", "etf_prices_daily", "etf_prices_monthly",
    "etf_prices_weekly", "etf_signals", "factor_metrics",
    "financials_annual_balance", "financials_annual_cashflow", "financials_annual_income",
    "financials_quarterly_balance", "financials_quarterly_cashflow", "financials_quarterly_income",
    "financials_ttm_cashflow", "financials_ttm_income",
    "growth_metrics", "industry_ranking", "key_metrics",
    "market_overview", "naaim_data", "quality_metrics", "relative_performance",
    "sectors", "signals_daily", "signals_etf_daily", "signals_etf_monthly", "signals_etf_weekly",
    "signals_monthly", "signals_weekly", "social_sentiment",
    "stock_prices_daily", "stock_prices_monthly", "stock_prices_weekly", "stock_scores",
    "stock_symbols", "swing_trader_scores", "trend_template_data", "value_metrics"
]

def extract_error_from_logs(log_group_name):
    """Extract last error message from loader logs."""
    try:
        response = logs.filter_log_events(
            logGroupName=log_group_name,
            startTime=int((datetime.now() - timedelta(hours=2)).timestamp() * 1000),
            limit=100
        )

        events = response.get('events', [])
        if not events:
            return None

        # Look for error patterns in last 20 messages
        error_patterns = ['error', 'failed', 'exception', 'traceback', 'timeout', 'killed']
        for event in reversed(events[-20:]):
            message = event['message'].lower()
            if any(pattern in message for pattern in error_patterns):
                return event['message'][:200]

        # Return last message if no error found
        if events:
            return events[-1]['message'][:200]
        return None

    except Exception as e:
        return f"Error reading logs: {str(e)[:100]}"

def main():
    print("\n" + "="*80)
    print("FAILURE ROOT CAUSE ANALYSIS")
    print(f"Analyzed: {len(FAILING_LOADERS)} loaders")
    print("="*80 + "\n")

    error_categories = defaultdict(list)

    for loader in sorted(FAILING_LOADERS):
        log_group = f"/ecs/algo-{loader}-loader"
        error = extract_error_from_logs(log_group)

        if error:
            # Categorize error
            if 'date' in error.lower() and 'time' in error.lower():
                category = "DATE/TIME PARSING"
            elif 'http' in error.lower() and '404' in error.lower():
                category = "API NOT FOUND"
            elif 'connection' in error.lower() or 'timeout' in error.lower():
                category = "CONNECTION/TIMEOUT"
            elif 'memory' in error.lower() or 'killed' in error.lower():
                category = "RESOURCE EXHAUSTION"
            elif 'no data' in error.lower() or 'not found' in error.lower():
                category = "DATA MISSING"
            else:
                category = "OTHER"

            error_categories[category].append((loader, error))
            print(f"[{category:<20}] {loader:<30} {error}")
        else:
            print(f"[NO ERROR LOG      ] {loader:<30} (no recent logs found)")

    print("\n" + "="*80)
    print("ERROR SUMMARY BY CATEGORY:")
    print("="*80)
    for category in sorted(error_categories.keys()):
        count = len(error_categories[category])
        print(f"\n{category} ({count}):")
        for loader, _ in error_categories[category][:5]:
            print(f"  - {loader}")
        if count > 5:
            print(f"  ... and {count-5} more")

    return 0

if __name__ == '__main__':
    import sys
    sys.exit(main())
