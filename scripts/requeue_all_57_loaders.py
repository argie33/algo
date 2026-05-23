#!/usr/bin/env python3
"""Re-queue all 57 loaders after Docker rebuild."""

import boto3
import time
from datetime import datetime

ecs = boto3.client('ecs', region_name='us-east-1')

ALL_57_LOADERS = [
    "aaiidata", "algo_metrics_daily", "analyst_sentiment", "analyst_upgrades_downgrades",
    "company_profile", "earnings_calendar", "earnings_history", "earnings_revisions",
    "earnings_sp500", "earnings_surprise", "econ_data", "eod_bulk_refresh",
    "etf_prices_daily", "etf_prices_monthly", "etf_prices_weekly", "etf_signals",
    "factor_metrics", "feargreed", "financials_annual_balance", "financials_annual_cashflow",
    "financials_annual_income", "financials_quarterly_balance", "financials_quarterly_cashflow",
    "financials_quarterly_income", "financials_ttm_cashflow", "financials_ttm_income",
    "growth_metrics", "industry_ranking", "key_metrics", "market_health_daily", "market_indices",
    "market_overview", "naaim_data", "quality_metrics", "relative_performance", "seasonality",
    "sectors", "signals_daily", "signals_etf_daily", "signals_etf_monthly", "signals_etf_weekly",
    "signals_monthly", "signals_weekly", "social_sentiment", "stock_prices_daily", "stock_prices_monthly",
    "stock_prices_weekly", "stock_scores", "stock_symbols", "swing_trader_scores", "technical_data_daily",
    "trend_template_data", "value_metrics"
]

def queue_loader(loader_name):
    task_def = f"algo-{loader_name}-loader"
    try:
        response = ecs.run_task(
            cluster='algo-cluster',
            taskDefinition=task_def,
            launchType='FARGATE',
            networkConfiguration={
                'awsvpcConfiguration': {
                    'subnets': ['subnet-0ccb7db133dd4071e'],
                    'securityGroups': ['sg-0ddae70a1a80b54bd'],
                    'assignPublicIp': 'ENABLED'
                }
            }
        )
        return bool(response['tasks'])
    except Exception as e:
        print(f"ERROR {loader_name}: {e}")
        return False

print(f"[{datetime.now().strftime('%H:%M:%S')}] Re-queuing all {len(ALL_57_LOADERS)} loaders...")
queued = 0
failed = []

for loader in ALL_57_LOADERS:
    if queue_loader(loader):
        queued += 1
        if queued % 10 == 0:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Queued {queued}/{len(ALL_57_LOADERS)}...")
        time.sleep(0.5)
    else:
        failed.append(loader)

print(f"\n[{datetime.now().strftime('%H:%M:%S')}] RESULT: {queued}/{len(ALL_57_LOADERS)} queued successfully")
if failed:
    print(f"Failed to queue: {failed}")
