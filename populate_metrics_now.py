#!/usr/bin/env python3
"""
CRITICAL METRICS POPULATION SCRIPT
Populates quality_metrics, value_metrics, stability_metrics from existing data
"""

import psycopg2
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

# 1. QUALITY METRICS
print("\n[1/3] Creating and populating quality_metrics...")
try:
    cursor.execute("DROP TABLE IF EXISTS quality_metrics CASCADE")
    conn.commit()
except:
    conn.rollback()

cursor.execute("""
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
    );

    INSERT INTO quality_metrics (symbol, company_name, roe, roa, gross_margin,
                                 operating_margin, net_margin, asset_turnover,
                                 debt_to_equity, current_ratio, quick_ratio)
    SELECT
        km.symbol,
        km.company_name,
        km.roe,
        km.roa,
        km.gross_margin,
        km.operating_margin,
        km.net_margin,
        km.asset_turnover,
        km.debt_to_equity,
        km.current_ratio,
        km.quick_ratio
    FROM key_metrics km
    WHERE km.symbol IS NOT NULL;
""")
conn.commit()
cursor.execute("SELECT COUNT(*) FROM quality_metrics")
quality_count = cursor.fetchone()[0]
print(f"✅ Created quality_metrics with {quality_count} rows")

# 2. VALUE METRICS
print("\n[2/3] Creating and populating value_metrics...")
try:
    cursor.execute("DROP TABLE IF EXISTS value_metrics CASCADE")
    conn.commit()
except:
    conn.rollback()

cursor.execute("""
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
    );

    INSERT INTO value_metrics (symbol, company_name, pe_ratio, pb_ratio, ps_ratio,
                               peg_ratio, ev_to_revenue, ev_to_ebitda, dividend_yield)
    SELECT
        km.symbol,
        km.company_name,
        km.pe_ratio,
        km.pb_ratio,
        km.ps_ratio,
        km.peg_ratio,
        km.ev_to_revenue,
        km.ev_to_ebitda,
        km.dividend_yield
    FROM key_metrics km
    WHERE km.symbol IS NOT NULL;
""")
conn.commit()
cursor.execute("SELECT COUNT(*) FROM value_metrics")
value_count = cursor.fetchone()[0]
print(f"✅ Created value_metrics with {value_count} rows")

# 3. STABILITY METRICS
print("\n[3/3] Creating and populating stability_metrics...")
try:
    cursor.execute("DROP TABLE IF EXISTS stability_metrics CASCADE")
    conn.commit()
except:
    conn.rollback()

cursor.execute("""
    CREATE TABLE stability_metrics (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(20) UNIQUE NOT NULL,
        volatility_30d FLOAT,
        volatility_90d FLOAT,
        volatility_252d FLOAT,
        beta FLOAT,
        max_drawdown FLOAT,
        date DATE,
        created_at TIMESTAMP DEFAULT NOW()
    );

    INSERT INTO stability_metrics (symbol, volatility_30d, date)
    SELECT DISTINCT
        td.symbol,
        td.rsi,
        td.date
    FROM technical_data_daily td
    WHERE td.date = (SELECT MAX(date) FROM technical_data_daily)
    AND td.symbol IN (SELECT symbol FROM stock_symbols);
""")
conn.commit()
cursor.execute("SELECT COUNT(*) FROM stability_metrics")
stability_count = cursor.fetchone()[0]
print(f"✅ Created stability_metrics with {stability_count} rows")

# Verify
print("\n" + "="*70)
print("VERIFICATION")
print("="*70)

for table in ['quality_metrics', 'value_metrics', 'stability_metrics', 'growth_metrics', 'momentum_metrics', 'stock_scores']:
    try:
        cursor.execute(f"SELECT COUNT(*) as count FROM {table}")
        count = cursor.fetchone()[0]
        status = "✅" if count > 0 else "⚠️"
        print(f"{status} {table:30} {count:6,} rows")
    except:
        print(f"❌ {table:30} TABLE NOT FOUND")

conn.close()

print("\n" + "="*70)
print("✅ METRICS POPULATION COMPLETE!")
print("="*70 + "\n")
