#!/usr/bin/env python3
"""Invoke all loaders as ECS tasks."""

import boto3
import sys

# All 43 loaders
LOADERS = [
    "stock_symbols", "stock_prices_daily", "etf_prices_daily", "etf_prices_weekly", "etf_prices_monthly",
    "trend_template_data", "financials_annual_income", "financials_annual_balance", "financials_annual_cashflow",
    "financials_quarterly_income", "financials_quarterly_balance", "financials_quarterly_cashflow",
    "financials_ttm_income", "financials_ttm_cashflow", "growth_metrics", "quality_metrics", "value_metrics",
    "earnings_history", "earnings_revisions", "earnings_surprise", "earnings_calendar", "company_profile",
    "analyst_sentiment", "analyst_upgrades_downgrades", "sectors", "industry_ranking", "seasonality",
    "signals_daily", "signals_weekly", "signals_monthly", "signals_etf_daily", "signals_etf_weekly", "signals_etf_monthly",
    "algo_metrics_daily", "market_data_batch", "technical_data_daily", "market_health_daily", "swing_trader_scores",
    "feargreed", "aaiidata", "naaim_data", "stock_scores", "eod_bulk_refresh"
]

def invoke_loaders(subnet, security_group):
    """Invoke all loaders as ECS tasks."""
    client = boto3.client('ecs', region_name='us-east-1')

    success = 0
    failed = 0

    for loader in LOADERS:
        task_def = f"algo-{loader}-loader"
        print(f"Invoking {loader}...", flush=True)

        try:
            response = client.run_task(
                cluster='algo-cluster',
                taskDefinition=task_def,
                launchType='FARGATE',
                networkConfiguration={
                    'awsvpcConfiguration': {
                        'subnets': [subnet],
                        'securityGroups': [security_group],
                        'assignPublicIp': 'ENABLED'
                    }
                }
            )

            if response['tasks']:
                print(f"  ✅ Task launched", flush=True)
                success += 1
            else:
                print(f"  ❌ Failed: No tasks returned", flush=True)
                failed += 1
        except Exception as e:
            print(f"  ❌ Failed: {str(e)}", flush=True)
            failed += 1

    print("")
    print("=== Summary ===")
    print(f"Launched: {success}")
    print(f"Failed: {failed}")
    print(f"Total: {success + failed}")

    return 0 if failed == 0 else 1

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: invoke_all_loaders.py <subnet> <security_group>")
        sys.exit(1)

    subnet = sys.argv[1]
    security_group = sys.argv[2]
    sys.exit(invoke_loaders(subnet, security_group))
