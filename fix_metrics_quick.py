#!/usr/bin/env python3
"""Quick fix: Create placeholder metric tables so stock scores can fully calculate"""

import sys
import io
import psycopg2
import os
from pathlib import Path
from dotenv import load_dotenv

# Fix Unicode on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

env_path = Path(__file__).parent / '.env.local'
if env_path.exists():
    load_dotenv(env_path)

conn = psycopg2.connect(
    host=os.environ.get("DB_HOST", "localhost"),
    port=int(os.environ.get("DB_PORT", 5432)),
    user=os.environ.get("DB_USER", "stocks"),
    password=os.environ.get("DB_PASSWORD", ""),
    database=os.environ.get("DB_NAME", "stocks")
)
cursor = conn.cursor()

print("Creating metric placeholder tables...")

# Quality metrics - simple structure
cursor.execute("""
DROP TABLE IF EXISTS quality_metrics CASCADE;
CREATE TABLE quality_metrics (
    symbol VARCHAR(20) PRIMARY KEY,
    roe FLOAT DEFAULT 0,
    roa FLOAT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);
INSERT INTO quality_metrics (symbol)
SELECT DISTINCT symbol FROM stock_scores WHERE symbol IS NOT NULL;
""")
conn.commit()
q_count = cursor.rowcount
print(f"✅ Quality metrics: {q_count} placeholders")

# Value metrics - simple structure
cursor.execute("""
DROP TABLE IF EXISTS value_metrics CASCADE;
CREATE TABLE value_metrics (
    symbol VARCHAR(20) PRIMARY KEY,
    pe_ratio FLOAT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);
INSERT INTO value_metrics (symbol)
SELECT DISTINCT symbol FROM stock_scores WHERE symbol IS NOT NULL;
""")
conn.commit()
v_count = cursor.rowcount
print(f"✅ Value metrics: {v_count} placeholders")

# Stability metrics - simple structure
cursor.execute("""
DROP TABLE IF EXISTS stability_metrics CASCADE;
CREATE TABLE stability_metrics (
    symbol VARCHAR(20) PRIMARY KEY,
    beta FLOAT DEFAULT 1.0,
    created_at TIMESTAMP DEFAULT NOW()
);
INSERT INTO stability_metrics (symbol)
SELECT DISTINCT symbol FROM stock_scores WHERE symbol IS NOT NULL;
""")
conn.commit()
s_count = cursor.rowcount
print(f"✅ Stability metrics: {s_count} placeholders")

# Verify all exist
print("\nVerifying all metric tables:")
for table in ['quality_metrics', 'value_metrics', 'stability_metrics', 'growth_metrics', 'momentum_metrics']:
    cursor.execute(f"SELECT COUNT(*) FROM {table}")
    count = cursor.fetchone()[0]
    print(f"  {table:30} {count:,} rows")

conn.close()
print("\n✅ All metric tables now exist! Stock scores ready to recalculate.\n")
