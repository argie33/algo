#!/usr/bin/env python
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv('.env.local')

# Get DB credentials
db_config = {
    'dbname': os.getenv('DB_NAME', 'algo_db'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432))
}

print("=" * 80)
print("DATABASE STATE CHECK")
print("=" * 80)

try:
    with psycopg2.connect(**db_config) as conn:
        with conn.cursor() as cur:
            # List all tables first
            cur.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            tables = [row[0] for row in cur.fetchall()]

            print("\nAVAILABLE TABLES:")
            for table in sorted(tables):
                print(f"  - {table}")

            # Check latest orchestrator run status
            if 'orchestrator_runs' in tables:
                cur.execute("SELECT run_id, status FROM orchestrator_runs ORDER BY started_at DESC LIMIT 3")
                print("\nRECENT ORCHESTRATOR RUNS:")
                for row in cur.fetchall():
                    print(f"  {row[0]}: status={row[1]}")

            # Check phase statuses for latest run
            if 'phase_status' in tables:
                cur.execute("""
                    SELECT phase_number, status, error_message
                    FROM phase_status
                    WHERE run_id=(SELECT run_id FROM orchestrator_runs ORDER BY started_at DESC LIMIT 1)
                    ORDER BY phase_number
                """)
                print("\nPHASE STATUSES (latest run):")
                for row in cur.fetchall():
                    err = f"  (error: {row[2][:80]})" if row[2] else ""
                    print(f"  Phase {row[0]}: {row[1]}{err}")

            # Check if there are any stuck transactions
            cur.execute("""
                SELECT pid, usename, state, query
                FROM pg_stat_activity
                WHERE state != 'idle' AND datname = current_database()
            """)
            results = cur.fetchall()
            if results:
                print("\nACTIVE TRANSACTIONS:")
                for row in results:
                    print(f"  PID {row[0]} ({row[1]}): {row[2]}")
                    print(f"    Query: {row[3][:100]}")
            else:
                print("\nACTIVE TRANSACTIONS: None")

            # Count open positions
            if 'algo_positions' in tables:
                cur.execute("""
                    SELECT COUNT(*) as open_count
                    FROM algo_positions
                    WHERE status='open'
                """)
                pos_count = cur.fetchone()[0]
                print(f"\nPOSITION STATUS:")
                print(f"  Open positions: {pos_count}")

            # Check signal quality distribution
            cur.execute("""
                SELECT COUNT(*),
                       ROUND(AVG(signal_quality_score)::numeric, 1) as avg_score,
                       MAX(signal_quality_score) as max_score,
                       MIN(signal_quality_score) as min_score,
                       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY signal_quality_score) as median_score
                FROM algo_signals
                WHERE signal_date >= CURRENT_DATE
            """)
            row = cur.fetchone()
            print(f"\nTODAY'S SIGNAL QUALITY:")
            print(f"  Count: {row[0]}")
            print(f"  Avg: {row[1]}")
            print(f"  Max: {row[2]}")
            print(f"  Min: {row[3]}")
            print(f"  Median: {row[4]}")

            # Check price loader status
            cur.execute("""
                SELECT loader_name, status, completion_pct, last_update_time
                FROM loader_status
                WHERE loader_name IN ('price_daily', 'price_weekly', 'price_monthly')
                ORDER BY loader_name
            """)
            print(f"\nPRICE LOADER STATUS:")
            for row in cur.fetchall():
                print(f"  {row[0]}: {row[1]} ({row[2]:.1f}%) updated {row[3]}")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
