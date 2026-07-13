#!/usr/bin/env python3
"""Check actual data freshness to identify real issues."""
import psycopg2
from datetime import datetime, timedelta
import sys
import io

if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

try:
    print("[FRESHNESS] Data Age Check")
    print("=" * 80)
    print()

    now = datetime.now()

    tables = [
        ('price_daily', 'signal_date', 'Price data'),
        ('technical_data_daily', 'date', 'Technical indicators'),
        ('market_health_daily', 'date', 'Market health'),
        ('stock_scores', 'updated_at', 'Stock scores'),
        ('algo_signals', 'signal_date', 'Signals'),
        ('algo_orchestrator_runs', 'started_at', 'Orchestrator runs'),
    ]

    for table, date_col, desc in tables:
        try:
            # Fresh connection per query to avoid transaction issues
            conn = psycopg2.connect(
                dbname='stocks',
                user='stocks',
                password='stockspassword',
                host='localhost',
                connect_timeout=5
            )
            cur = conn.cursor()
            cur.execute(f"SELECT MAX({date_col}) FROM {table}")
            latest = cur.fetchone()[0]
            cur.close()
            conn.close()
            if latest:
                age_hours = (now - latest).total_seconds() / 3600
                age_days = age_hours / 24

                # Color code: green if <4h, yellow if <1d, red if >1d
                if age_hours < 4:
                    status = "✓ FRESH"
                elif age_hours < 24:
                    status = "⚠ OLD (>4h)"
                else:
                    status = "✗ STALE (>1d)"

                if age_days < 1:
                    time_str = f"{age_hours:.1f}h"
                else:
                    time_str = f"{age_days:.1f}d"

                print(f"{status:20} {desc:25} {time_str:>8} old")
            else:
                print(f"✗ EMPTY                {desc:25} NO DATA")
        except Exception as e:
            print(f"✗ ERROR                {desc:25} {type(e).__name__}")

    print()
    print("[THRESHOLD] Phase 1 requires:")
    print("  - price_daily: <1h old")
    print("  - technical_data_daily: <24h old")
    print("  - market_health_daily: <24h old")

except Exception as e:
    print(f"[FATAL] {type(e).__name__}: {e}")
    sys.exit(1)
