#!/usr/bin/env python3
"""Check AWS orchestrator and data status"""

import psycopg2
from datetime import datetime, timedelta

try:
    conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
    cur = conn.cursor()

    # Check orchestrator runs
    cur.execute("SELECT COUNT(*) as runs FROM algo_orchestrator_runs WHERE started_at > NOW() - INTERVAL '1 day'")
    result = cur.fetchone()
    print(f"Orchestrator runs (last 24h): {result[0]}")

    cur.execute("SELECT MAX(started_at) as latest FROM algo_orchestrator_runs")
    result = cur.fetchone()
    if result[0]:
        age = datetime.utcnow() - result[0].replace(tzinfo=None)
        print(f"Latest orchestrator run: {result[0]}")
        print(f"Age: {age.total_seconds() / 3600:.1f} hours")

    # Check Phase 9 snapshots
    cur.execute("SELECT COUNT(*) as snapshots FROM algo_portfolio_snapshots WHERE snapshot_date >= CURRENT_DATE - INTERVAL '7 days'")
    result = cur.fetchone()
    print(f"\nPortfolio snapshots (last 7 days): {result[0]}")

    cur.execute("SELECT MAX(snapshot_date) as latest FROM algo_portfolio_snapshots")
    result = cur.fetchone()
    if result[0]:
        print(f"Latest snapshot: {result[0]}")

    # Check data freshness
    print("\n=== DATA FRESHNESS ===")
    cur.execute("SELECT symbol, MAX(date) as latest_date FROM price_daily GROUP BY symbol ORDER BY latest_date DESC LIMIT 1")
    result = cur.fetchone()
    if result:
        print(f"Price data: {result[0]} = {result[1]}")

    cur.execute("SELECT MAX(updated_at) FROM growth_metrics")
    result = cur.fetchone()
    if result[0]:
        print(f"Growth metrics: {result[0]}")

    cur.execute("SELECT MAX(updated_at) FROM quality_metrics")
    result = cur.fetchone()
    if result[0]:
        print(f"Quality metrics: {result[0]}")

    # Check halt reasons (recent halts)
    print("\n=== RECENT HALTS ===")
    cur.execute("SELECT COUNT(*) FROM algo_orchestrator_runs WHERE halt_reason IS NOT NULL AND started_at > NOW() - INTERVAL '24 hours'")
    result = cur.fetchone()
    print(f"Halts in last 24h: {result[0]}")

    cur.execute("SELECT halt_reason, COUNT(*) as count FROM algo_orchestrator_runs WHERE halt_reason IS NOT NULL GROUP BY halt_reason ORDER BY count DESC LIMIT 5")
    for row in cur.fetchall():
        print(f"  {row[0][:60]}... ({row[1]} runs)")

    cur.close()
    conn.close()

except Exception as e:
    print(f'Error: {e}')
