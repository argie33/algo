#!/usr/bin/env python3
"""Initialize database schema - create all required tables"""

import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

# Load environment
env_path = Path(__file__).parent / '.env.local'
if env_path.exists():
    load_dotenv(env_path)

# Database config
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_PORT = os.environ.get('DB_PORT', '5432')
DB_NAME = os.environ.get('DB_NAME', 'algo')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASSWORD = os.environ.get('DB_PASSWORD', '')

# Connect to database
conn = psycopg2.connect(
    host=DB_HOST,
    port=DB_PORT,
    database=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD
)
cursor = conn.cursor()

# Create technical_data_daily table
cursor.execute("""
    CREATE TABLE IF NOT EXISTS technical_data_daily (
        symbol VARCHAR(20) NOT NULL,
        date DATE NOT NULL,
        rsi FLOAT,
        macd FLOAT,
        macd_signal FLOAT,
        macd_hist FLOAT,
        mom FLOAT,
        roc FLOAT,
        roc_10d FLOAT,
        roc_20d FLOAT,
        roc_60d FLOAT,
        roc_120d FLOAT,
        roc_252d FLOAT,
        mansfield_rs FLOAT,
        adx FLOAT,
        plus_di FLOAT,
        minus_di FLOAT,
        created_at TIMESTAMP DEFAULT NOW(),
        PRIMARY KEY (symbol, date)
    )
""")
print("[OK] Created technical_data_daily table")

# Create quality_metrics table (if not exists - same as in loadfactormetrics.py)
cursor.execute("""
    CREATE TABLE IF NOT EXISTS quality_metrics (
        symbol VARCHAR(50) NOT NULL,
        date DATE NOT NULL,
        return_on_equity_pct FLOAT,
        return_on_assets_pct FLOAT,
        return_on_invested_capital_pct FLOAT,
        gross_margin_pct FLOAT,
        operating_margin_pct FLOAT,
        profit_margin_pct FLOAT,
        fcf_to_net_income FLOAT,
        operating_cf_to_net_income FLOAT,
        debt_to_equity FLOAT,
        current_ratio FLOAT,
        quick_ratio FLOAT,
        earnings_surprise_avg FLOAT,
        eps_growth_stability FLOAT,
        payout_ratio FLOAT,
        earnings_beat_rate FLOAT,
        estimate_revision_direction FLOAT,
        consecutive_positive_quarters INT,
        surprise_consistency FLOAT,
        earnings_growth_4q_avg FLOAT,
        revision_activity_30d FLOAT,
        estimate_momentum_60d FLOAT,
        estimate_momentum_90d FLOAT,
        revision_trend_score FLOAT,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_at TIMESTAMP DEFAULT NOW(),
        PRIMARY KEY (symbol, date)
    )
""")
print("[OK] Created quality_metrics table")

conn.commit()
cursor.close()
conn.close()
print("[OK] Schema initialization complete")
