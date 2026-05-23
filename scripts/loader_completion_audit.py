#!/usr/bin/env python3
"""Audit loader completion status and generate comprehensive report."""

import boto3
import json
from collections import defaultdict
from datetime import datetime

ecs = boto3.client('ecs', region_name='us-east-1')

LOADERS = [
    "aaiidata", "algo_metrics_daily", "analyst_sentiment", "analyst_upgrades_downgrades",
    "company_profile", "earnings_calendar", "earnings_history", "earnings_revisions",
    "earnings_surprise", "econ_data", "eod_bulk_refresh", "etf_prices_daily",
    "etf_prices_monthly", "etf_prices_weekly", "feargreed", "financials_annual_balance",
    "financials_annual_cashflow", "financials_annual_income", "financials_quarterly_balance",
    "financials_quarterly_cashflow", "financials_quarterly_income", "financials_ttm_cashflow",
    "financials_ttm_income", "growth_metrics", "industry_ranking", "key_metrics",
    "market_data_batch", "market_health_daily", "market_indices", "naaim_data",
    "quality_metrics", "seasonality", "sectors", "signals_daily",
    "signals_etf_daily", "signals_etf_monthly", "signals_etf_weekly", "signals_monthly",
    "signals_weekly", "stock_prices_daily", "stock_prices_monthly", "stock_prices_weekly",
    "stock_scores", "stock_symbols", "swing_trader_scores", "technical_data_daily",
    "trend_template_data", "value_metrics",
]


def get_loader_task_results():
    """Get latest task result for each loader."""
    results = {}

    # Get all stopped tasks
    response = ecs.list_tasks(cluster='algo-cluster', desiredStatus='STOPPED', maxResults=100)
    task_arns = response.get('taskArns', [])

    if task_arns:
        desc = ecs.describe_tasks(cluster='algo-cluster', tasks=task_arns)

        # Group by loader and get latest
        by_loader = defaultdict(list)
        for task in desc.get('tasks', []):
            task_def_arn = task['taskDefinitionArn']
            task_def_name = task_def_arn.split('/')[-1]
            loader = task_def_name.split(':')[0].replace('algo-', '').replace('-loader', '')

            exit_code = task['containers'][0].get('exitCode') if task['containers'] else None
            by_loader[loader].append({
                'exit_code': exit_code,
                'stopped_at': task.get('stoppingAt', task.get('stoppedAt', 0))
            })

        # Get latest for each loader
        for loader, attempts in by_loader.items():
            latest = sorted(attempts, key=lambda x: x['stopped_at'], reverse=True)[0]
            results[loader] = {
                'status': 'PASS' if latest['exit_code'] == 0 else f'FAIL({latest["exit_code"]})',
                'exit_code': latest['exit_code']
            }

    return results


def print_report():
    """Print comprehensive audit report."""
    results = get_loader_task_results()

    # Categorize loaders
    passing = []
    failing = []
    not_run = []

    for loader in LOADERS:
        if loader in results:
            if results[loader]['status'] == 'PASS':
                passing.append(loader)
            else:
                failing.append(loader)
        else:
            not_run.append(loader)

    print("=" * 70)
    print("LOADER COMPLETION AUDIT")
    print("=" * 70)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    print(f"PASSING: {len(passing)}/{len(LOADERS)}")
    for loader in sorted(passing):
        print(f"  [PASS] {loader}")

    print(f"\nFAILING: {len(failing)}/{len(LOADERS)}")
    for loader in sorted(failing):
        status = results[loader]['status']
        print(f"  [{status}] {loader}")

    print(f"\nNOT RUN: {len(not_run)}/{len(LOADERS)}")
    for loader in sorted(not_run):
        print(f"  [PENDING] {loader}")

    print(f"\n{'=' * 70}")
    pct = 100 * len(passing) / len(LOADERS) if LOADERS else 0
    print(f"TOTAL: {len(passing)} passing, {len(failing)} failing, {len(not_run)} pending")
    print(f"Completion Rate: {pct:.1f}%")
    print("=" * 70)


if __name__ == '__main__':
    print_report()
