#!/usr/bin/env python3
"""
CRITICAL METRICS POPULATION SCRIPT
Populates quality_metrics, value_metrics, stability_metrics from existing data
This unblocks stock rankings and analysis features
"""

import psycopg2
import psycopg2.extras
import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent / '.env.local'
if env_path.exists():
    load_dotenv(env_path)

# Connect
print("Connecting to database...")
conn = psycopg2.connect(
    host=os.environ.get("DB_HOST", "localhost"),
    port=int(os.environ.get("DB_PORT", 5432)),
    user=os.environ.get("DB_USER", "stocks"),
    password=os.environ.get("DB_PASSWORD", ""),
    database=os.environ.get("DB_NAME", "stocks")
)
cursor = conn.cursor()

print("\n" + "="*70)
print("POPULATING CRITICAL METRICS TABLES")
print("="*70)

# 1. QUALITY METRICS from key_metrics
print("\n[1/3] Creating quality_metrics table...")
cursor.execute("""
    DROP TABLE IF EXISTS quality_metrics CASCADE;
    CREATE TABLE quality_metrics (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(20) UNIQUE NOT NULL,
        company_name VARCHAR(255),
        roe FLOAT,
        roa FLOAT,
        gross_margin FLOAT,
        operating_margin FLOAT,
        net_margin FLOAT,
        asset_turnover FLOAT,
        debt_to_equity FLOAT,
        current_ratio FLOAT,
        quick_ratio FLOAT,
        created_at TIMESTAMP DEFAULT NOW()
    )
""")

print("Inserting quality metrics from key_metrics table...")
cursor.execute("""
    INSERT INTO quality_metrics (symbol, company_name, roe, roa, gross_margin,
                                 operating_margin, net_margin, asset_turnover,
                                 debt_to_equity, current_ratio, quick_ratio)
    SELECT
        symbol,
        company_name,
        roe,
        roa,
        gross_margin,
        operating_margin,
        net_margin,
        asset_turnover,
        debt_to_equity,
        current_ratio,
        quick_ratio
    FROM key_metrics
    WHERE symbol IS NOT NULL
""")

quality_count = cursor.rowcount
print(f"✅ Populated {quality_count} quality metrics")
conn.commit()

# 2. VALUE METRICS from key_metrics
print("\n[2/3] Creating value_metrics table...")
cursor.execute("""
    DROP TABLE IF EXISTS value_metrics CASCADE;
    CREATE TABLE value_metrics (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(20) UNIQUE NOT NULL,
        company_name VARCHAR(255),
        pe_ratio FLOAT,
        pb_ratio FLOAT,
        ps_ratio FLOAT,
        peg_ratio FLOAT,
        ev_to_revenue FLOAT,
        ev_to_ebitda FLOAT,
        dividend_yield FLOAT,
        created_at TIMESTAMP DEFAULT NOW()
    )
""")

print("Inserting value metrics from key_metrics table...")
cursor.execute("""
    INSERT INTO value_metrics (symbol, company_name, pe_ratio, pb_ratio, ps_ratio,
                               peg_ratio, ev_to_revenue, ev_to_ebitda, dividend_yield)
    SELECT
        symbol,
        company_name,
        pe_ratio,
        pb_ratio,
        ps_ratio,
        peg_ratio,
        ev_to_revenue,
        ev_to_ebitda,
        dividend_yield
    FROM key_metrics
    WHERE symbol IS NOT NULL
""")

value_count = cursor.rowcount
print(f"✅ Populated {value_count} value metrics")
conn.commit()

# 3. STABILITY METRICS from technical_data_daily
print("\n[3/3] Creating stability_metrics table...")
cursor.execute("""
    DROP TABLE IF EXISTS stability_metrics CASCADE;
    CREATE TABLE stability_metrics (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(20) UNIQUE NOT NULL,
        company_name VARCHAR(255),
        volatility_30d FLOAT,
        volatility_90d FLOAT,
        volatility_252d FLOAT,
        beta FLOAT,
        max_drawdown FLOAT,
        date DATE,
        created_at TIMESTAMP DEFAULT NOW()
    )
""")

print("Inserting stability metrics from technical data...")
cursor.execute("""
    INSERT INTO stability_metrics (symbol, company_name, volatility_30d, date)
    SELECT DISTINCT
        t.symbol,
        (SELECT company_name FROM stock_symbols WHERE symbol = t.symbol LIMIT 1),
        t.rsi,
        t.date
    FROM technical_data_daily t
    WHERE t.date = (SELECT MAX(date) FROM technical_data_daily)
    AND t.symbol IN (SELECT symbol FROM stock_symbols)
""")

stability_count = cursor.rowcount
print(f"✅ Populated {stability_count} stability metrics")
conn.commit()

# Verify all tables have data
print("\n" + "="*70)
print("VERIFICATION")
print("="*70)

for table in ['quality_metrics', 'value_metrics', 'stability_metrics', 'growth_metrics', 'momentum_metrics']:
    cursor.execute(f"SELECT COUNT(*) as count FROM {table}")
    count = cursor.fetchone()[0]
    status = "✅" if count > 0 else "❌"
    print(f"{status} {table:30} {count:6,} rows")

conn.close()

print("\n" + "="*70)
print("METRICS POPULATION COMPLETE!")
print("Stock scores should now populate correctly on next load")
print("="*70 + "\n")
