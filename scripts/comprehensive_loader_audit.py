#!/usr/bin/env python3
"""Comprehensive loader audit after execution completes."""

import boto3
import json
from collections import defaultdict
from datetime import datetime

ecs = boto3.client('ecs', region_name='us-east-1')

EXPECTED_LOADERS = {
    "aaiidata", "algo_metrics_daily", "analyst_sentiment", "analyst_upgrades_downgrades",
    "company_profile", "earnings_calendar", "earnings_history", "earnings_revisions",
    "earnings_sp500", "earnings_surprise", "econ_data", "eod_bulk_refresh",
    "etf_prices_daily", "etf_prices_monthly", "etf_prices_weekly", "etf_signals",
    "factor_metrics", "feargreed", "financials_annual_balance", "financials_annual_cashflow",
    "financials_annual_income", "financials_quarterly_balance", "financials_quarterly_cashflow",
    "financials_quarterly_income", "financials_ttm_cashflow", "financials_ttm_income",
    "growth_metrics", "industry_ranking", "key_metrics", "market_data_batch", "market_health_daily",
    "market_indices", "market_overview", "naaim_data", "quality_metrics", "relative_performance",
    "seasonality", "sectors", "signals_daily", "signals_etf_daily", "signals_etf_monthly",
    "signals_etf_weekly", "signals_monthly", "signals_weekly", "social_sentiment",
    "stock_prices_daily", "stock_prices_monthly", "stock_prices_weekly", "stock_scores",
    "stock_symbols", "swing_trader_scores", "technical_data_daily", "trend_template_data",
    "value_metrics"
}

def get_comprehensive_status():
    """Get detailed status of all loaders."""
    # Get all stopped tasks
    stopped_resp = ecs.list_tasks(cluster='algo-cluster', desiredStatus='STOPPED', maxResults=100)
    running_resp = ecs.list_tasks(cluster='algo-cluster', desiredStatus='RUNNING', maxResults=100)

    all_tasks = []
    stopped_arns = stopped_resp.get('taskArns', [])
    running_arns = running_resp.get('taskArns', [])

    # Process stopped tasks
    for i in range(0, len(stopped_arns), 10):
        batch = stopped_arns[i:i+10]
        if batch:
            resp = ecs.describe_tasks(cluster='algo-cluster', tasks=batch)
            all_tasks.extend(resp['tasks'])

    # Process running tasks
    for i in range(0, len(running_arns), 10):
        batch = running_arns[i:i+10]
        if batch:
            resp = ecs.describe_tasks(cluster='algo-cluster', tasks=batch)
            all_tasks.extend(resp['tasks'])

    # Organize by loader name, keeping most recent attempt
    loader_status = defaultdict(lambda: {'attempts': [], 'best_run': None})

    for task in all_tasks:
        task_def_arn = task['taskDefinitionArn']
        parts = task_def_arn.split('/')[-1].split(':')[0]

        if parts.startswith('algo-') and parts.endswith('-loader'):
            loader_name = parts[5:-7]
            exit_code = task.get('containers', [{}])[0].get('exitCode')
            status = task['lastStatus']
            stopped_at = task.get('stoppedAt', 0)

            attempt = {
                'exit_code': exit_code,
                'status': status,
                'stopped_at': stopped_at,
                'stop_reason': task.get('stopCode', 'RUNNING')
            }

            loader_status[loader_name]['attempts'].append(attempt)

            # Track best run (exit code 0, most recent)
            if exit_code == 0:
                if not loader_status[loader_name]['best_run'] or stopped_at > loader_status[loader_name]['best_run']['stopped_at']:
                    loader_status[loader_name]['best_run'] = attempt

    # Categorize results
    passing = []
    failing = []
    running = []
    pending = []

    for loader_name in sorted(EXPECTED_LOADERS):
        status = loader_status.get(loader_name, {})

        if not status['attempts']:
            pending.append(loader_name)
        elif any(a['status'] == 'RUNNING' for a in status['attempts']):
            running.append(loader_name)
        elif status['best_run']:
            passing.append(loader_name)
        else:
            failing.append((loader_name, status['attempts'][-1] if status['attempts'] else None))

    return passing, failing, running, pending, loader_status

def main():
    print("\n" + "="*80)
    print("COMPREHENSIVE LOADER AUDIT")
    print(f"Time: {datetime.now().isoformat()}")
    print("="*80)

    passing, failing, running, pending, all_status = get_comprehensive_status()

    print(f"\n✓ PASSING ({len(passing)}):")
    for l in passing:
        print(f"  ✓ {l}")

    print(f"\n✗ FAILING ({len(failing)}):")
    for l, attempt in failing:
        reason = f"({attempt['exit_code']})" if attempt and attempt['exit_code'] else "(no data)"
        print(f"  ✗ {l} {reason}")

    print(f"\n⏱ RUNNING ({len(running)}):")
    for l in running[:10]:
        print(f"  ⏱ {l}")
    if len(running) > 10:
        print(f"  ... and {len(running)-10} more")

    print(f"\n⏸ PENDING ({len(pending)}):")
    for l in pending[:5]:
        print(f"  ⏸ {l}")
    if len(pending) > 5:
        print(f"  ... and {len(pending)-5} more")

    print(f"\n" + "="*80)
    print(f"SUMMARY: {len(passing)}/{len(EXPECTED_LOADERS)} passing, {len(failing)} failing, {len(running)} running, {len(pending)} pending")
    print("="*80 + "\n")

    return 0

if __name__ == '__main__':
    import sys
    sys.exit(main())
