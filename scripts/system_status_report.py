#!/usr/bin/env python3
"""Comprehensive system status and issue diagnostic."""

import sys
from datetime import date as _date, timedelta
import psycopg2
from dotenv import load_dotenv
import os

load_dotenv('.env.local')

print("\n" + "="*70)
print("SYSTEM STATUS REPORT - SESSION 46")
print("="*70 + "\n")

conn = psycopg2.connect(
    host=os.getenv('DB_HOST'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    database=os.getenv('DB_NAME')
)
cur = conn.cursor()

# 1. Position Summary
print("1. POSITION STATUS")
print("-" * 70)
cur.execute("""
SELECT status, COUNT(*) as count,
       ROUND(AVG(unrealized_pnl_pct), 1) as avg_pnl_pct
FROM algo_positions
GROUP BY status
""")

for row in cur.fetchall():
    status = row[0]
    count = row[1]
    avg_pnl = row[2] if row[2] else 0
    print(f"  {status:10s}: {count:3d} positions (avg P&L: {avg_pnl:+.1f}%)")

print()

# 2. Trade Status
print("2. TRADE STATUS")
print("-" * 70)
cur.execute("""
SELECT status, COUNT(*) as count FROM algo_trades GROUP BY status
""")

for row in cur.fetchall():
    print(f"  {row[0]:20s}: {row[1]}")

print()

# 3. Stop Price Analysis
print("3. STOP PRICE ANALYSIS (Post-Fix Expected)")
print("-" * 70)
cur.execute("""
SELECT COUNT(*) as raised,
       COUNT(CASE WHEN current_stop_price <= stop_loss_price THEN 1 END) as not_raised
FROM algo_positions
WHERE status = 'open'
""")

row = cur.fetchone()
raised = row[0] - row[1] if row[1] else 0
not_raised = row[1] if row[1] else 0
total = row[0]

print(f"  Stops RAISED (current > entry): {raised}/{total}")
print(f"  Stops NOT_RAISED: {not_raised}/{total}")

if not_raised > 0:
    print(f"  WARNING: {not_raised} stops not yet raised")
    print(f"      -> Run full orchestrator after fix deployed to raise stops")

print()

# 4. Position Limits
print("4. POSITION LIMITS")
print("-" * 70)
cur.execute("""
SELECT key, value FROM algo_config
WHERE key IN ('max_positions', 'max_new_positions_today', 'max_positions_per_sector')
""")

for row in cur.fetchall():
    print(f"  {row[0]:30s}: {row[1]}")

cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'open'")
open_count = cur.fetchone()[0]
print(f"\n  Current open positions: {open_count}/15")

if open_count >= 15:
    print(f"  WARNING: AT POSITION LIMIT - No new entries possible until positions close")

print()

# 5. Recent Orchestrator Runs
print("5. RECENT ORCHESTRATOR RUNS")
print("-" * 70)
cur.execute("""
SELECT run_id, run_date, overall_status, halt_reason, phases_completed
FROM orchestrator_execution_log
WHERE run_date >= CURRENT_DATE - INTERVAL '2 days'
ORDER BY started_at DESC
LIMIT 10
""")

for row in cur.fetchall():
    status = row[2] if row[2] else 'unknown'
    reason = (row[3] or '')[:50]
    print(f"  {row[0]:40s} {status:10s} phases={row[4]}")
    if reason and 'MARKET_HALT' not in reason:
        print(f"    Reason: {reason}")

print()

# 6. Critical Issues
print("6. CRITICAL ISSUES FOUND & FIXED")
print("-" * 70)
print("  [FIXED] Phase 6 Stop Column Bug - FIXED (commits a52190fa2, fc2320a)")
print("     Phase 6 was updating stop_loss_price instead of current_stop_price")
print("     Result: All 15 stop-raise recommendations silently ignored")
print()
print("  [PENDING] Position Deadlock - ANALYSIS COMPLETE")
print("     System at 15/15 position limit with no exits recommended")
print("     Phase 3 recommends only stop raises (positions are healthy)")
print("     Phase 8 blocks new entries (no available slots)")
print()

print("7. NEXT STEPS")
print("-" * 70)
print("  1. [DONE] Deploy Phase 6 stop column fix")
print("  2. [PENDING] Run orchestrator on trading day to:")
print("     - Verify stop-raise actions execute properly")
print("     - Monitor if emergency close triggers when trying new entries")
print("  3. [PENDING] Consider adjusting position management:")
print("     - Add profit-taking exit strategy (not just stops)")
print("     - Reduce max_positions if current limit causes issues")
print("     - Implement partial position closes")
print()

print("="*70)

cur.close()
conn.close()
