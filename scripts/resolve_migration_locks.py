#!/usr/bin/env python3
"""
Resolve database locks blocking migrations.
Terminates long-running queries that may be holding locks.
"""

import json
import subprocess
import sys
import time


def get_db_credentials():
    """Fetch RDS credentials from Secrets Manager."""
    result = subprocess.run(
        [
            "aws", "secretsmanager", "get-secret-value",
            "--secret-id", "algo-db-credentials-dev",
            "--region", "us-east-1",
            "--query", "SecretString",
            "--output", "text"
        ],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"❌ Error fetching credentials: {result.stderr}")
        return None
    return json.loads(result.stdout)


def terminate_blocking_pids():
    """Terminate long-running queries to release locks."""
    try:
        import psycopg2
    except ImportError:
        print("⚠️  psycopg2 not available - cannot connect to database from this system")
        print("Run this script from a Linux/Unix system with psycopg2 installed")
        return False

    creds = get_db_credentials()
    if not creds:
        return False

    try:
        conn = psycopg2.connect(
            host=creds['host'],
            port=creds['port'],
            database=creds['dbname'],
            user=creds['username'],
            password=creds['password'],
            connect_timeout=5
        )
        cur = conn.cursor()

        print(f"✓ Connected to {creds['host']}:{creds['port']}/{creds['dbname']}")

        # Find long-running queries (> 30 seconds)
        cur.execute("""
            SELECT pid, usename, state, query, extract(epoch FROM (now() - query_start)) as duration_secs
            FROM pg_stat_activity
            WHERE state != 'idle'
              AND pid != pg_backend_pid()
              AND query_start < now() - interval '30 seconds'
            ORDER BY query_start ASC;
        """)

        long_running = cur.fetchall()
        if not long_running:
            print("✓ No long-running queries found")
            conn.close()
            return True

        print(f"\n⚠️  Found {len(long_running)} long-running query/queries:")
        for pid, user, state, query, duration in long_running:
            print(f"  PID {pid} ({user}): {state} for {duration:.0f}s")
            print(f"    Query: {query[:100]}")

        # Terminate them
        print("\nTerminating long-running queries...")
        for pid, user, state, query, duration in long_running:
            cur.execute("SELECT pg_terminate_backend(%s);", (pid,))
            result = cur.fetchone()[0]
            if result:
                print(f"  ✓ Terminated PID {pid}")
            else:
                print(f"  ⚠️  Could not terminate PID {pid} (may have ended already)")

        conn.commit()
        conn.close()
        print("\n✓ Database locks resolved")
        return True

    except Exception as e:
        print(f"❌ Database error: {e}")
        return False


def main():
    print("=" * 60)
    print("DATABASE LOCK RESOLVER")
    print("=" * 60)

    if not terminate_blocking_pids():
        sys.exit(1)

    print("\n" + "=" * 60)
    print("Next steps:")
    print("1. Re-run the deployment workflow:")
    print("   gh workflow run deploy-all-infrastructure.yml --repo argie33/algo --ref main --field skip_terraform=true")
    print("2. Monitor the migrations job:")
    print("   gh run watch <run-id> --repo argie33/algo")
    print("=" * 60)


if __name__ == "__main__":
    main()
