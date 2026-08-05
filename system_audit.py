#!/usr/bin/env python3
"""Comprehensive system audit to find all issues."""
import sys
from pathlib import Path
from datetime import datetime, timedelta

_project_root = Path(__file__).parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from utils.dotenv_loader import load_env_local
load_env_local()

from utils.db import DatabaseContext

def audit():
    with DatabaseContext('read') as cur:
        print("="*80)
        print("SYSTEM AUDIT - Finding Issues")
        print("="*80)

        # 1. Check for invalid positions
        print("\n1. CHECKING POSITIONS:")
        cur.execute("""
            SELECT COUNT(*) as cnt, status, COUNT(CASE WHEN current_price IS NULL THEN 1 END) as null_prices
            FROM algo_positions
            GROUP BY status
        """)
        for row in cur.fetchall():
            status = row['status']
            count = row['cnt']
            null_count = row['null_prices']
            print(f"  {status:20} {count:5} positions ({null_count} missing prices)")

        # 2. Check for stale or stuck trades
        print("\n2. CHECKING TRADES:")
        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN closed_at IS NULL THEN 1 END) as open,
                COUNT(CASE WHEN closed_at IS NULL AND filled_at < now() - interval '7 days' THEN 1 END) as stale_open
            FROM algo_trades
        """)
        row = cur.fetchone()
        if row:
            print(f"  Total trades: {row.get('total', 0)}")
            print(f"  Open trades: {row.get('open', 0)}")
            print(f"  Stale open trades (>7 days): {row.get('stale_open', 0)}")

        # 3. Check position-trade sync issues
        print("\n3. POSITION-TRADE SYNC:")
        cur.execute("""
            SELECT COUNT(*) as orphan_cnt
            FROM algo_positions p
            LEFT JOIN algo_trades t ON p.id = t.position_id AND t.closed_at IS NULL
            WHERE p.status = 'open' AND t.id IS NULL
        """)
        row = cur.fetchone()
        orphan_count = row.get('orphan_cnt', 0) if row else 0
        print(f"  Open positions without matching trade: {orphan_count}")

        # 4. Check config for issues
        print("\n4. CONFIGURATION:")
        cur.execute("""
            SELECT key, value
            FROM algo_config
            WHERE key IN ('execution_mode', 'alpaca_paper_trading', 'dry_run', 'max_total_risk_pct', 'max_position_size_pct')
            ORDER BY key
        """)
        for row in cur.fetchall():
            key = row['key']
            value = row['value']
            print(f"  {key:30} {value}")

        # 5. Check for any unfinished orchestrator runs
        print("\n5. RECENT ORCHESTRATOR RUNS:")
        cur.execute("""
            SELECT
                COUNT(*) as total_runs,
                COUNT(CASE WHEN overall_status = 'ok' THEN 1 END) as ok,
                COUNT(CASE WHEN overall_status = 'degraded' THEN 1 END) as degraded,
                COUNT(CASE WHEN overall_status IN ('halted', 'error') THEN 1 END) as failed
            FROM orchestrator_execution_log
            WHERE created_at > now() - interval '24 hours'
        """)
        row = cur.fetchone()
        if row:
            print(f"  Last 24h runs: {row.get('total_runs', 0)} (ok: {row.get('ok', 0)}, degraded: {row.get('degraded', 0)}, failed: {row.get('failed', 0)})")

        # 6. Check circuit breaker status
        print("\n6. CIRCUIT BREAKER STATUS:")
        cur.execute("""
            SELECT is_halted, halt_reason, updated_at
            FROM circuit_breaker_status
            ORDER BY updated_at DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        if row:
            print(f"  Halted: {row['is_halted']}")
            if row['halt_reason']:
                print(f"  Reason: {row['halt_reason'][:100]}")
            print(f"  Updated: {row['updated_at']}")

        # 7. Check for data freshness issues
        print("\n7. DATA FRESHNESS:")
        cur.execute("""
            SELECT
                table_name,
                MAX(load_timestamp) as last_load,
                NOW() - MAX(load_timestamp) as age
            FROM data_loader_status
            WHERE is_complete = true
            GROUP BY table_name
            ORDER BY age DESC
            LIMIT 10
        """)
        for row in cur.fetchall():
            age_seconds = row['age'].total_seconds()
            if age_seconds < 3600:
                age_str = f"{int(age_seconds/60)} min"
            else:
                age_str = f"{int(age_seconds/3600)} hr"
            print(f"  {row['table_name']:35} {age_str} old")

        # 8. Check for any unhandled errors in logs
        print("\n8. RECENT ERRORS (last 1hr):")
        cur.execute("""
            SELECT COUNT(*) as err_count, action_type
            FROM algo_audit_log
            WHERE entity_type = 'error' AND created_at > now() - interval '1 hour'
            GROUP BY action_type
            ORDER BY COUNT(*) DESC
        """)
        rows = cur.fetchall()
        if rows:
            for row in rows:
                print(f"  {row.get('action_type', 'UNKNOWN'):40} {row.get('err_count', 0)}")
        else:
            print("  No recent errors logged")

if __name__ == '__main__':
    audit()
