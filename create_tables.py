#!/usr/bin/env python3
"""Create missing dashboard tables."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

os.environ['DB_HOST'] = 'localhost'
os.environ['DB_PORT'] = '5432'
os.environ['DB_NAME'] = 'stocks'
os.environ['DB_USER'] = 'stocks'
os.environ['DB_PASSWORD'] = 'stocks'

from utils.db_connection import get_db_connection

conn = get_db_connection()
cur = conn.cursor()

print("Creating missing dashboard tables...")
print("=" * 70)

# Circuit breaker log
try:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS circuit_breaker_log (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            breaker_name VARCHAR(100) NOT NULL,
            status VARCHAR(20) NOT NULL,
            reason TEXT,
            value FLOAT,
            threshold FLOAT,
            action VARCHAR(50),
            details JSONB
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_circuit_breaker_log_created ON circuit_breaker_log(created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_circuit_breaker_log_breaker ON circuit_breaker_log(breaker_name)")
    print("[OK] circuit_breaker_log created")
except Exception as e:
    print(f"[ERR] circuit_breaker_log: {e}")

# Data patrol log
try:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS algo_data_patrol (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            patrol_id VARCHAR(50),
            check_type VARCHAR(100),
            status VARCHAR(20),
            severity VARCHAR(20),
            message TEXT,
            details JSONB,
            symbol VARCHAR(20),
            table_name VARCHAR(100)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_algo_data_patrol_created ON algo_data_patrol(created_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_algo_data_patrol_severity ON algo_data_patrol(severity)")
    print("[OK] algo_data_patrol created")
except Exception as e:
    print(f"[ERR] algo_data_patrol: {e}")

# Performance daily
try:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS performance_daily (
            id SERIAL PRIMARY KEY,
            date DATE NOT NULL UNIQUE,
            equity_value FLOAT,
            daily_return FLOAT,
            cumulative_return FLOAT,
            max_drawdown FLOAT,
            sharpe_ratio FLOAT,
            win_rate FLOAT,
            trades_count INT,
            winning_trades INT,
            losing_trades INT,
            avg_win FLOAT,
            avg_loss FLOAT,
            profit_factor FLOAT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            details JSONB
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_performance_daily_date ON performance_daily(date DESC)")
    print("[OK] performance_daily created")
except Exception as e:
    print(f"[ERR] performance_daily: {e}")

conn.commit()

# Verify
print("\n" + "=" * 70)
print("Verifying tables...")

cur.execute("""
    SELECT tablename FROM pg_tables
    WHERE schemaname = 'public'
    AND tablename IN ('circuit_breaker_log', 'algo_data_patrol', 'performance_daily')
    ORDER BY tablename
""")

tables = cur.fetchall()
if len(tables) == 3:
    print("[OK] All 3 missing tables created successfully:")
    for table in tables:
        print(f"     - {table[0]}")
else:
    print(f"[WARN] Only {len(tables)}/3 tables found")

cur.close()
conn.close()

print("\n" + "=" * 70)
print("Dashboard table setup COMPLETE")
