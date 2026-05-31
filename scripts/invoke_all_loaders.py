#!/usr/bin/env python3
"""Invoke all loaders as ECS tasks."""

import boto3
import sys

# All loaders from terraform/modules/loaders/main.tf loader_file_map
LOADERS = [
    # Reference data
    "stock_symbols", "sp500_constituents", "russell2000_constituents",
    # Pricing data
    "stock_prices_daily",
    # Financial statements
    "financials_annual_income", "financials_annual_balance", "financials_annual_cashflow",
    "financials_quarterly_income", "financials_quarterly_balance", "financials_quarterly_cashflow",
    "financials_ttm_income", "financials_ttm_cashflow",
    # Computed metrics
    "growth_metrics", "quality_metrics", "value_metrics", "positioning_metrics", "stability_metrics",
    "stock_scores",
    # Earnings data
    "earnings_history", "earnings_calendar",
    # Company & analyst data
    "company_profile", "analyst_sentiment", "analyst_upgrades_downgrades",
    "industry_ranking", "sector_ranking", "sector_performance",
    "economic_calendar",
    # Market sentiment
    "feargreed", "aaiidata", "naaim_data",
    # Sentiment aggregation
    "sentiment", "sentiment_aggregate",
    # Trading signals & scores
    "signal_themes", "signal_quality_scores", "buy_sell_daily",
    # Technical indicators & metrics
    "technical_data_daily", "algo_metrics_daily", "swing_trader_scores",
    # Market health & economic data
    "market_health_daily", "fred_economic_data", "trend_template_data",
    # Seasonality stats
    "seasonality",
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
                        'assignPublicIp': 'DISABLED'
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
