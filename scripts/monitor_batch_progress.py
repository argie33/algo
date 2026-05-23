#!/usr/bin/env python3
"""Monitor batch loader progress in real-time."""

import boto3
import time
import sys
from datetime import datetime
from collections import defaultdict

ecs = boto3.client('ecs', region_name='us-east-1')
logs = boto3.client('logs', region_name='us-east-1')

ALL_LOADERS = [
    "stock_symbols", "sectors", "company_profile", "market_indices",
    "aaiidata", "feargreed", "econ_data", "market_health_daily",
    "analyst_sentiment", "analyst_upgrades_downgrades", "earnings_calendar",
    "earnings_history", "earnings_revisions", "earnings_surprise", "stock_scores",
    "stock_prices_daily", "stock_prices_monthly", "stock_prices_weekly",
    "etf_prices_daily", "etf_prices_monthly", "etf_prices_weekly",
    "technical_data_daily", "algo_metrics_daily", "growth_metrics", "key_metrics",
    "quality_metrics", "value_metrics", "swing_trader_scores",
    "financials_annual_balance", "financials_annual_cashflow", "financials_annual_income",
    "financials_quarterly_balance", "financials_quarterly_cashflow", "financials_quarterly_income",
    "financials_ttm_cashflow", "financials_ttm_income",
    "signals_daily", "signals_weekly", "signals_monthly",
    "signals_etf_daily", "signals_etf_weekly", "signals_etf_monthly",
    "eod_bulk_refresh", "naaim_data", "seasonality", "trend_template_data",
    "industry_ranking"
]

def get_loader_status(loader_name):
    """Check status of a loader from CloudWatch logs."""
    log_group = f"/ecs/algo-{loader_name}-loader"
    try:
        # Get most recent log stream
        response = logs.describe_log_streams(
            logGroupName=log_group,
            orderBy='LastEventTime',
            descending=True,
            maxItems=1
        )

        if not response.get('logStreams'):
            return 'PENDING'

        stream = response['logStreams'][0]

        # Get latest events
        events = logs.get_log_events(
            logGroupName=log_group,
            logStreamName=stream['logStreamName'],
            limit=50
        )

        if not events.get('events'):
            return 'RUNNING'

        messages = [e['message'] for e in events['events']]
        full_text = ' '.join(messages).lower()

        # Check for completion/failure indicators
        if any(x in full_text for x in ['complete', 'success', 'successfully', 'inserted', 'rows']):
            return 'DONE'
        elif any(x in full_text for x in ['error', 'failed', 'exception', 'timed out', 'timeout', 'traceback']):
            return 'FAILED'
        else:
            return 'RUNNING'

    except:
        return 'UNKNOWN'

def monitor_progress():
    """Display continuous progress update."""
    status_map = defaultdict(list)

    while True:
        try:
            # Get running tasks
            running_tasks = ecs.list_tasks(cluster='algo-cluster')
            running_count = len(running_tasks.get('taskArns', []))

            # Check status of all loaders
            status_map.clear()
            for loader in ALL_LOADERS:
                status = get_loader_status(loader)
                status_map[status].append(loader)

            # Display
            now = datetime.now().strftime('%H:%M:%S')
            done = len(status_map.get('DONE', []))
            running = len(status_map.get('RUNNING', []))
            failed = len(status_map.get('FAILED', []))
            other = len(status_map.get('PENDING', [])) + len(status_map.get('UNKNOWN', []))
            total = done + running + failed + other

            pct = int((done / total) * 100) if total > 0 else 0

            print(f"\n[{now}] Progress: {pct}% ({done}/{total} complete)")
            print(f"  ✓ Done: {done} | ▶ Running: {running} | ✗ Failed: {failed} | ? Other: {other}")
            print(f"  ECS running tasks: {running_tasks.get('taskArns', [])}")

            if failed > 0:
                print(f"\n  Failed loaders:")
                for loader in status_map.get('FAILED', [])[:5]:
                    print(f"    - {loader}")
                if failed > 5:
                    print(f"    ... and {failed-5} more")

            if running == 0 and done < total:
                print(f"\n  ⚠ WARNING: {done + failed + other} loaders not running, {done} done")

            # If all done, show summary
            if done == total:
                print(f"\n✓ ALL LOADERS COMPLETE!")
                if failed > 0:
                    print(f"  {failed} failed - review CloudWatch logs")
                break

            time.sleep(30)

        except KeyboardInterrupt:
            print("\nMonitoring stopped")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(10)

if __name__ == '__main__':
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting loader progress monitor")
    print(f"Tracking {len(ALL_LOADERS)} loaders")
    monitor_progress()
