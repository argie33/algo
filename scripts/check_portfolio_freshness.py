#!/usr/bin/env python3
"""Check portfolio data freshness after Phase 9 execution."""

import os
import sys
from datetime import date, datetime

import psycopg2

try:
    conn = psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5432"),
        database=os.environ.get("DB_NAME", "algo"),
        user=os.environ.get("DB_USER"),
        password=os.environ.get("DB_PASSWORD")
    )
    cur = conn.cursor()

    print("=" * 70)
    print("PORTFOLIO DATA FRESHNESS CHECK")
    print("=" * 70)
    print()

    # Check latest portfolio snapshot
    cur.execute("""
        SELECT snapshot_date, created_at, total_portfolio_value, position_count
        FROM algo_portfolio_snapshots
        ORDER BY created_at DESC
        LIMIT 1
    """)

    row = cur.fetchone()
    if row:
        snap_date, created_at, tpv, pos_count = row
        age_days = (date.today() - snap_date).days

        # Determine freshness
        is_today = snap_date == date.today()
        status = "✅ FRESH" if is_today else f"⚠️  STALE ({age_days} days old)"

        print("Latest Portfolio Snapshot:")
        print(f"  Date: {snap_date} {status}")
        print(f"  Created: {created_at}")
        print(f"  TPV: ${tpv:,.2f}")
        print(f"  Positions: {pos_count}")
        print()

        if is_today:
            print("✅ SUCCESS - Portfolio data is FRESH!")
            sys.exit(0)
        else:
            print(f"⚠️  Portfolio data is {age_days} days old (expected today)")
    else:
        print("❌ ERROR: No portfolio snapshots found!")
        sys.exit(1)

    # Check recent orchestrator runs
    cur.execute("""
        SELECT run_id, phase, status, summary, created_at
        FROM orchestrator_execution_log
        ORDER BY created_at DESC
        LIMIT 5
    """)

    print("Recent Orchestrator Runs:")
    for run_id, phase, status, summary, created_at in cur.fetchall():
        elapsed = (datetime.now(created_at.tzinfo) - created_at).total_seconds() / 60
        print(f"  Phase {phase} ({elapsed:>5.0f}m ago): {status:6} - {run_id}")
        if summary:
            print(f"    └─ {summary[:60]}")

    conn.close()

except psycopg2.Error as e:
    print(f"❌ Database Error: {e}")
    print("Make sure DB_USER, DB_PASSWORD, DB_HOST, DB_PORT env vars are set")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error: {type(e).__name__}: {e}")
    sys.exit(1)
