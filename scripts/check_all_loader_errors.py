#!/usr/bin/env python3
"""
Comprehensive loader error analysis across all loaders.
Identifies timeout, rate limit, and data collection issues.
"""

import boto3
from datetime import datetime, timedelta
from collections import defaultdict

def check_all_loaders():
    logs = boto3.client('logs', region_name='us-east-1')

    all_loaders = [
        '/ecs/algo-stock_prices_daily-loader',
        '/ecs/algo-technical_data_daily-loader',
        '/ecs/algo-buy_sell_daily-loader',
        '/ecs/algo-signal_quality_scores-loader',
        '/ecs/algo-algo_metrics_daily-loader',
        '/ecs/algo-swing_trader_scores-loader',
        '/ecs/algo-company_profile-loader',
        '/ecs/algo-stability_metrics-loader',
        '/ecs/algo-analyst_sentiment-loader',
        '/ecs/algo-analyst_upgrades_downgrades-loader',
        '/ecs/algo-market_health_daily-loader',
        '/ecs/algo-trend_template_data-loader',
        '/ecs/algo-fred_economic_data-loader',
        '/ecs/algo-growth_metrics-loader',
        '/ecs/algo-quality_metrics-loader',
        '/ecs/algo-value_metrics-loader',
    ]

    start_time = int((datetime.utcnow() - timedelta(hours=96)).timestamp() * 1000)

    print("=" * 80)
    print("COMPREHENSIVE LOADER ERROR ANALYSIS (Last 96 hours)")
    print("=" * 80)

    loader_issues = defaultdict(lambda: {
        'connection_timeout': [],
        'statement_timeout': [],
        'rate_limit': [],
        'failed_download': [],
        'module_error': [],
        'other_error': [],
    })

    for lg in all_loaders:
        loader_name = lg.split('/')[-1].replace('-loader', '')

        try:
            response = logs.filter_log_events(
                logGroupName=lg,
                startTime=start_time,
                limit=200
            )

            events = response.get('events', [])
            if not events:
                continue

            for event in events:
                msg = event['message']
                msg_lower = msg.lower()
                ts = datetime.fromtimestamp(event['timestamp'] / 1000).strftime('%Y-%m-%d %H:%M')

                if 'timed-out waiting' in msg_lower and 'connection' in msg_lower:
                    loader_issues[loader_name]['connection_timeout'].append((ts, msg[:80]))
                elif 'statement timeout' in msg_lower or 'canceling statement' in msg_lower:
                    loader_issues[loader_name]['statement_timeout'].append((ts, msg[:80]))
                elif 'rate' in msg_lower and ('limit' in msg_lower or 'too many' in msg_lower):
                    loader_issues[loader_name]['rate_limit'].append((ts, msg[:80]))
                elif 'failed download' in msg_lower:
                    loader_issues[loader_name]['failed_download'].append((ts, msg[:80]))
                elif 'no module named' in msg_lower:
                    loader_issues[loader_name]['module_error'].append((ts, msg[:80]))
                elif 'error' in msg_lower or 'failed' in msg_lower or 'exception' in msg_lower:
                    loader_issues[loader_name]['other_error'].append((ts, msg[:80]))

        except Exception as e:
            print(f"Error checking {loader_name}: {str(e)[:60]}")

    # Print detailed results
    print("\nDETAILED LOADER STATUS:")
    print("-" * 80)

    for loader_name in sorted(loader_issues.keys()):
        issues = loader_issues[loader_name]
        total = sum(len(v) for v in issues.values())

        if total == 0:
            print(f"{loader_name}: OK (no errors)")
        else:
            print(f"\n{loader_name}: [ERROR] {total} errors")

            if issues['connection_timeout']:
                print(f"  Connection timeout: {len(issues['connection_timeout'])} occurrences")
                for ts, msg in issues['connection_timeout'][:2]:
                    print(f"    [{ts}] {msg}...")

            if issues['statement_timeout']:
                print(f"  Statement timeout: {len(issues['statement_timeout'])} occurrences")
                for ts, msg in issues['statement_timeout'][:2]:
                    print(f"    [{ts}] {msg}...")

            if issues['rate_limit']:
                print(f"  Rate limit: {len(issues['rate_limit'])} occurrences")

            if issues['failed_download']:
                print(f"  Failed downloads: {len(issues['failed_download'])} occurrences")

            if issues['module_error']:
                print(f"  Module errors: {len(issues['module_error'])} occurrences")
                for ts, msg in issues['module_error'][:1]:
                    print(f"    [{ts}] {msg}...")

            if issues['other_error']:
                print(f"  Other errors: {len(issues['other_error'])} occurrences")

    # Summary statistics
    print("\n" + "=" * 80)
    print("ERROR SUMMARY")
    print("=" * 80)

    total_by_type = defaultdict(int)
    for loader_issues_detail in loader_issues.values():
        for error_type, errors in loader_issues_detail.items():
            total_by_type[error_type] += len(errors)

    print(f"Connection timeouts:   {total_by_type['connection_timeout']}")
    print(f"Statement timeouts:    {total_by_type['statement_timeout']}")
    print(f"Rate limits:           {total_by_type['rate_limit']}")
    print(f"Failed downloads:      {total_by_type['failed_download']}")
    print(f"Module errors:         {total_by_type['module_error']}")
    print(f"Other errors:          {total_by_type['other_error']}")
    print(f"Total errors:          {sum(total_by_type.values())}")

    # Identify critical issues
    print("\n" + "=" * 80)
    print("CRITICAL ISSUES NEEDING ATTENTION")
    print("=" * 80)

    critical = []
    for loader_name, issues in loader_issues.items():
        if issues['connection_timeout']:
            critical.append(f"{loader_name}: Connection pool exhaustion ({len(issues['connection_timeout'])} times)")
        if issues['statement_timeout']:
            critical.append(f"{loader_name}: Statement timeout ({len(issues['statement_timeout'])} times)")
        if issues['module_error']:
            critical.append(f"{loader_name}: Module import error")

    if critical:
        for issue in critical:
            print(f"[CRITICAL] {issue}")
    else:
        print("[OK] No critical issues detected in logs")

if __name__ == '__main__':
    check_all_loaders()
