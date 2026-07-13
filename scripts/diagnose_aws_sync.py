#!/usr/bin/env python3
"""Diagnose AWS/Local Database Sync Issues

Usage:
  python3 scripts/diagnose_aws_sync.py
"""

import sys

import psycopg2
import requests


def check_local_db():
    print("\n" + "="*70)
    print("LOCAL DATABASE STATE")
    print("="*70)

    try:
        conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
        cur = conn.cursor()

        # Check positions
        cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status='open'")
        pos_count = cur.fetchone()[0]

        # Check portfolio
        cur.execute("SELECT total_portfolio_value FROM algo_portfolio_snapshots ORDER BY created_at DESC LIMIT 1")
        row = cur.fetchone()
        port_value = row[0] if row else None

        # Check orchestrator runs
        cur.execute("SELECT MAX(started_at), overall_status FROM algo_orchestrator_runs GROUP BY overall_status ORDER BY MAX(started_at) DESC LIMIT 1")
        rows = cur.fetchall()
        last_run = rows[0] if rows else (None, None)

        conn.close()

        print("[OK] Connected to localhost:5432/stocks")
        print(f"  Open positions: {pos_count}")
        if port_value:
            print(f"  Portfolio value: ${port_value:,.2f}")
        else:
            print("  Portfolio value: N/A")
        if last_run[0]:
            print(f"  Last orchestrator run: {last_run[0]} ({last_run[1]})")
        else:
            print("  Last orchestrator run: None")

        return {"positions": pos_count, "portfolio_value": port_value, "last_run": last_run}

    except Exception as e:
        print(f"[ERROR] {e}")
        return None

def check_aws_lambda_response():
    print("\n" + "="*70)
    print("AWS LAMBDA RESPONSE STATE")
    print("="*70)

    try:
        # Test portfolio endpoint
        response = requests.get('https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/algo/portfolio', timeout=10)
        response.raise_for_status()

        data = response.json()
        if data.get('statusCode') == 200 and data.get('data'):
            payload = data['data']
            print("[OK] Connected to AWS Lambda API")
            print(f"  Status: {data.get('statusCode')}")
            print(f"  Position count: {payload.get('position_count')}")
            print(f"  Portfolio value: ${payload.get('total_portfolio_value')}")
            print(f"  Data age: {payload.get('data_age_seconds')}s")

            return {
                "positions": payload.get('position_count'),
                "portfolio_value": float(payload.get('total_portfolio_value', 0)),
                "data_age_seconds": payload.get('data_age_seconds')
            }
        else:
            print(f"[ERROR] Invalid response: {data}")
            return None

    except Exception as e:
        print(f"[ERROR] {e}")
        return None

def check_data_sync():
    """Compare local vs AWS data."""
    print("\n" + "="*70)
    print("DATA SYNC ANALYSIS")
    print("="*70)

    local = check_local_db()
    aws = check_aws_lambda_response()

    if not local or not aws:
        print("\n[ERROR] Cannot compare: missing data from local or AWS")
        return

    print(f"\n{'Metric':<25} {'Local':<15} {'AWS':<15} {'Match':<10}")
    print("-" * 65)

    pos_match = "[OK]" if local['positions'] == aws['positions'] else "[MISMATCH]"
    print(f"{'Open Positions':<25} {local['positions']:<15} {aws['positions']:<15} {pos_match:<10}")

    local_port = float(local['portfolio_value']) if local['portfolio_value'] else 0
    aws_port = float(aws['portfolio_value']) if aws['portfolio_value'] else 0
    port_match = "[OK]" if abs(local_port - aws_port) < 1 else "[MISMATCH]"
    print(f"{'Portfolio Value':<25} ${local_port:>13,.2f} ${aws_port:>13,.2f} {port_match:<10}")

    if "[MISMATCH]" in pos_match or "[MISMATCH]" in port_match:
        print("\n[WARNING] DATA OUT OF SYNC")
        print("   Possible causes:")
        print("   1. Orchestrator runs locally only (doesn't update AWS RDS)")
        print("   2. AWS RDS hasn't been updated with latest trades")
        print("   3. Database connection/permissions issue in AWS")
        return False
    else:
        print("\n[OK] DATA IN SYNC")
        return True

def main():
    """Run diagnostics."""
    print("\nDIAGNOSING AWS/LOCAL DATABASE SYNC...\n")

    try:
        is_synced = check_data_sync()

        print("\n" + "="*70)
        print("RECOMMENDATIONS")
        print("="*70)

        if is_synced:
            print("\n[OK] Your system is synchronized. Dashboard can use AWS mode safely:")
            print("  python3 -m dashboard")
        else:
            print("\n[WARNING] Your system is OUT OF SYNC. Fix options:\n")
            print("Option 1: Use LOCAL mode for dashboard (recommended for dev):")
            print("  Terminal 1: python3 api-pkg/dev_server.py")
            print("  Terminal 2: python3 -m dashboard --local\n")
            print("Option 2: Sync AWS RDS with local data:")
            print("  python3 scripts/trigger_orchestrator.py --run morning --mode paper")
            print("  (Wait for orchestrator to complete, then test again)\n")
            print("Option 3: Manual database sync (if orchestrator doesn't work):")
            print("  pg_dump -h localhost -U stocks stocks > /tmp/dump.sql")
            print("  (Then restore to AWS RDS with proper credentials)")

        print("\n" + "="*70 + "\n")

    except KeyboardInterrupt:
        print("\n\nCancelled.")
        sys.exit(1)

if __name__ == '__main__':
    main()
