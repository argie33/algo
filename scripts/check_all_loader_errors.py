#!/usr/bin/env python3
"""
Comprehensive loader error analysis across all loaders.
Identifies timeout, rate limit, and data collection issues.
"""

import sys
import os
import boto3
from datetime import datetime, timedelta
from collections import defaultdict

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from terraform_helpers import get_infrastructure_names, get_loader_log_groups

def check_all_loaders():
    logs = boto3.client('logs', region_name='us-east-1')

    # Get infrastructure names dynamically
    names = get_infrastructure_names()
    log_groups = get_loader_log_groups(names)
    all_loaders = list(log_groups.values())

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
