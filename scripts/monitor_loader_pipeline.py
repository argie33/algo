#!/usr/bin/env python3
"""
Monitor loader pipeline execution and alert on failures.
Tracks morning and EOD pipeline runs, checks data freshness after completion.
"""

import time
from datetime import datetime

import boto3


def check_pipeline_execution(execution_arn: str) -> dict:
    """Get current execution status."""
    sfn = boto3.client('stepfunctions', region_name='us-east-1')

    try:
        response = sfn.describe_execution(executionArn=execution_arn)
        return {
            'status': response['status'],  # RUNNING | SUCCEEDED | FAILED | TIMED_OUT | ABORTED
            'started': response['startDate'],
            'stopped': response.get('stopDate'),
            'error': response.get('error'),
            'cause': response.get('cause'),
        }
    except Exception as e:
        return {'error': str(e)}

def check_data_freshness() -> dict:
    """Check if loader data is fresh."""
    from datetime import date

    import psycopg2

    conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
    cur = conn.cursor()

    today = date.today()

    try:
        tables = {
            'price_daily': f"SELECT COUNT(*) FROM price_daily WHERE date = '{today}'",
            'technical_data_daily': f"SELECT COUNT(*) FROM technical_data_daily WHERE date = '{today}'",
            'buy_sell_daily': f"SELECT COUNT(*) FROM buy_sell_daily WHERE date = '{today}'",
            'stock_scores': f"SELECT COUNT(*) FROM stock_scores WHERE date::date = '{today}'",
        }

        results = {}
        for table, query in tables.items():
            try:
                cur.execute(query)
                count = cur.fetchone()[0]
                results[table] = count
            except Exception as e:
                results[table] = f"ERROR: {e}"

        return results
    finally:
        cur.close()
        conn.close()

def main():
    """Monitor pipeline progress and data freshness."""

    # Execution from manual trigger
    execution_arn = 'arn:aws:states:us-east-1:626216981288:execution:algo-morning-prep-pipeline-dev:manual-recovery-20260712200938'

    print("=" * 80)
    print("LOADER PIPELINE MONITOR")
    print("=" * 80)
    print(f"\nTracking execution: {execution_arn.split(':')[-1]}")
    print("Started: 2026-07-12 20:09:35 UTC")
    print("Expected completion: 45-60 minutes (20:54:35 - 21:09:35 UTC)")
    print(f"Current time: {datetime.utcnow().isoformat()}Z\n")

    # Poll execution status
    max_wait_minutes = 90
    poll_interval_sec = 30
    elapsed_min = 0

    while elapsed_min < max_wait_minutes:
        status = check_pipeline_execution(execution_arn)

        if 'error' in status:
            print(f"❌ Error checking execution: {status['error']}")
            break

        current_status = status['status']
        elapsed_sec = (datetime.now(status['started'].tzinfo) - status['started']).total_seconds()
        elapsed_min = elapsed_sec / 60

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Status: {current_status:12} | Elapsed: {elapsed_min:6.1f} min | ", end='')

        if current_status == 'RUNNING':
            print("Pipeline executing...")
        elif current_status == 'SUCCEEDED':
            print("✓ Pipeline completed successfully!")
            print(f"\n  Stopped: {status['stopped']}")

            # Check data freshness
            print("\n  Checking data freshness...")
            freshness = check_data_freshness()

            print("\n  Data loaded:")
            for table, count in freshness.items():
                if isinstance(count, int):
                    status_symbol = "✓" if count > 100 else "⚠"
                    print(f"    {status_symbol} {table:<30} {count:>8,} rows")
                else:
                    print(f"    ✗ {table:<30} {count}")

            break
        elif current_status == 'FAILED':
            print("❌ Pipeline FAILED!")
            print(f"\n  Error: {status.get('error', 'Unknown')}")
            print(f"  Cause: {status.get('cause', 'No details')}")
            break
        elif current_status in ['TIMED_OUT', 'ABORTED']:
            print(f"❌ Pipeline {current_status}!")
            break

        time.sleep(poll_interval_sec)
        elapsed_min += poll_interval_sec / 60

    if elapsed_min >= max_wait_minutes:
        print(f"\n⏱ Timeout after {max_wait_minutes} minutes. Pipeline may still be running.")
        print("Check AWS console for status.")

    print("\n" + "=" * 80)

if __name__ == '__main__':
    main()
