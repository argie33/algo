#!/usr/bin/env python3
"""Simple endpoint tests - execute SQL queries to verify they work."""

import psycopg2

def test_query(name, query):
    """Test a single SQL query."""
    try:
        conn = psycopg2.connect(
            host='localhost',
            database='stocks',
            user='stocks',
            password=''
        )
        cur = conn.cursor()
        cur.execute(query)
        row = cur.fetchone()
        cur.close()
        conn.close()

        if row:
            print(f"[OK] {name}")
            return True
        else:
            print(f"[NO DATA] {name}")
            return False
    except Exception as e:
        print(f"[ERROR] {name}: {type(e).__name__}: {str(e)[:80]}")
        return False

print("=" * 80)
print("TESTING SQL QUERIES FOR FAILING ENDPOINTS")
print("=" * 80)
print()

# Test queries for each failing endpoint
tests = [
    ("algo_metrics", "SELECT 1 FROM algo_metrics_daily LIMIT 1"),
    ("circuit_breakers", "SELECT 1 FROM algo_circuit_breakers LIMIT 1"),
    ("notifications", "SELECT 1 FROM algo_notifications LIMIT 1"),
    ("audit_log", "SELECT 1 FROM algo_audit_log LIMIT 1"),
    ("sector_rotation", "SELECT 1 FROM algo_signals LIMIT 1"),  # Check if algo_signals exists
    ("rejection_funnel", "SELECT 1 FROM algo_signals LIMIT 1"),  # Check if algo_signals exists
    ("orchestrator_exec", "SELECT 1 FROM orchestrator_execution_log LIMIT 1"),
    ("market_sentiment", "SELECT 1 FROM market_sentiment LIMIT 1"),
]

passed = 0
failed = 0

for name, query in tests:
    if test_query(name, query):
        passed += 1
    else:
        failed += 1

print()
print("=" * 80)
print(f"Results: {passed} passed, {failed} failed")
print("=" * 80)
