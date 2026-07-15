#!/usr/bin/env python3
"""Monitor AWS Lambda orchestrator execution progress."""

import psycopg2
import sys
import time

def check_orchestrator_status():
    try:
        conn = psycopg2.connect(
            dbname='stocks',
            user='stocks',
            host='localhost',
            password=None
        )
        cur = conn.cursor()

        # Check for AWS/Lambda runs
        cur.execute("""
            SELECT run_id, started_at, completed_at, overall_status, halt_reason
            FROM algo_orchestrator_runs
            WHERE started_at > NOW() - INTERVAL '15 minutes'
            ORDER BY started_at DESC
            LIMIT 3
        """)

        runs = cur.fetchall()

        # Check growth scores
        cur.execute("""
            SELECT
              COUNT(*) as total,
              COUNT(CASE WHEN growth_score IS NOT NULL THEN 1 END) as with_score,
              MAX(updated_at) as latest_update
            FROM stock_scores
        """)
        total, with_score, latest = cur.fetchone()

        conn.close()

        return {
            'runs': runs,
            'total_scores': total,
            'with_score': with_score,
            'latest_update': latest
        }
    except Exception as e:
        return {'error': str(e)}

if __name__ == '__main__':
    print("[INFO] Monitoring AWS Lambda orchestrator execution...")
    print("[INFO] (Press Ctrl+C to stop)\n")

    iteration = 0
    while True:
        iteration += 1
        status = check_orchestrator_status()

        print(f"\n[{iteration:02d}] Status check at {time.strftime('%H:%M:%S')}")

        if 'error' in status:
            print(f"  ERROR: {status['error']}")
        else:
            runs = status['runs']
            if runs:
                print(f"  Recent runs:")
                for run_id, started, completed, status_val, halt in runs:
                    if completed:
                        print(f"    {run_id}: COMPLETED [{status_val}]")
                    else:
                        print(f"    {run_id}: IN PROGRESS (started {started})")
                    if halt:
                        print(f"      Halt: {halt[:60]}")

            total = status['total_scores']
            with_score = status['with_score']
            latest = status['latest_update']

            if total > 0:
                pct = 100 * with_score / total
                print(f"  Growth scores: {with_score}/{total} ({pct:.1f}%)")
                print(f"  Latest update: {latest}")

        print("  (Waiting 10 seconds...)", end='', flush=True)
        try:
            time.sleep(10)
        except KeyboardInterrupt:
            print("\n[INFO] Monitor stopped.")
            sys.exit(0)
