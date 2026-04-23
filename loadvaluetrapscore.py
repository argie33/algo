#!/usr/bin/env python3
"""
Value Trap Detection Score - Identifies suspicious "cheap" stocks
Scores: 0-100 (0=HIGH RISK TRAP, 100=SAFE/NO TRAP RISK)
"""
import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime
import logging
import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent / '.env.local'
if env_path.exists():
    load_dotenv(env_path)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_db_config():
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", 5432)),
        "user": os.environ.get("DB_USER", "stocks"),
        "password": os.environ.get("DB_PASSWORD", "bed0elAn"),
        "database": os.environ.get("DB_NAME", "stocks")
    }

def query(sql, params=None):
    config = get_db_config()
    conn = psycopg2.connect(**config)
    cursor = conn.cursor()
    cursor.execute(sql, params or [])
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result

def query_df(sql):
    config = get_db_config()
    return pd.read_sql(sql, psycopg2.connect(**config))

def calculate_trap_scores():
    """Calculate value trap risk scores for all stocks"""
    logger.info("Loading growth and quality metrics...")

    sql = """
    SELECT
      sc.symbol,
      sc.quality_score,
      sc.growth_score,
      sc.composite_score,
      gm.revenue_growth_yoy,
      gm.net_income_growth_yoy,
      gm.operating_income_growth_yoy,
      qm.fcf_to_net_income,
      qm.debt_to_equity,
      qm.earnings_beat_rate,
      qm.estimate_revision_direction
    FROM stock_scores sc
    LEFT JOIN growth_metrics gm ON gm.symbol = sc.symbol
    LEFT JOIN quality_metrics qm ON qm.symbol = sc.symbol
    WHERE sc.quality_score IS NOT NULL
    """

    df = query_df(sql)
    logger.info(f"Loaded data for {len(df)} stock records")

    # === 1. EARNINGS QUALITY SCORE (0-100) ===
    # RED FLAG: Earnings growing much faster than revenue (unsustainable)
    df['earnings_alignment_gap'] = 0

    def calc_earnings_quality(row):
        if pd.isna(row['revenue_growth_yoy']) or pd.isna(row['net_income_growth_yoy']):
            return 50  # Unknown

        rev_growth = float(row['revenue_growth_yoy'])
        ni_growth = float(row['net_income_growth_yoy'])
        gap = abs(ni_growth - rev_growth)

        # If NI declining while revenue positive = RED FLAG
        if rev_growth > 0 and ni_growth < 0:
            return 20  # Margin collapse trap

        # If NI growing > 100% faster than revenue = RED FLAG
        if gap > 100:
            return 25  # Unsustainable earnings

        # If NI growing 50-100% faster = CAUTION
        if gap > 50:
            return 40

        # If NI growing 25-50% faster = WATCH
        if gap > 25:
            return 60

        # Good alignment
        return 80

    df['earnings_quality_score'] = df.apply(calc_earnings_quality, axis=1)

    # === 2. CASH FLOW QUALITY SCORE (0-100) ===
    # RED FLAG: Earnings without cash backing (accounting tricks)
    def calc_cash_quality(row):
        if pd.isna(row['fcf_to_net_income']):
            return 50  # Unknown

        fcf_ratio = float(row['fcf_to_net_income'])

        # Negative FCF = huge trap
        if fcf_ratio < 0:
            return 10

        # FCF < 50% of NI = poor cash conversion
        if fcf_ratio < 0.5:
            return 30

        # FCF < 80% of NI = moderate
        if fcf_ratio < 0.8:
            return 60

        # Good cash conversion
        if fcf_ratio >= 1.0:
            return 90

        return 70

    df['cash_quality_score'] = df.apply(calc_cash_quality, axis=1)

    # === 3. BALANCE SHEET HEALTH SCORE (0-100) ===
    # RED FLAG: High debt + declining earnings = insolvency risk
    def calc_balance_sheet(row):
        if pd.isna(row['debt_to_equity']):
            return 50  # Unknown

        debt_ratio = float(row['debt_to_equity'])

        # Extreme leverage
        if debt_ratio > 2.0:
            return 20

        # High leverage
        if debt_ratio > 1.0:
            return 40

        # Moderate
        if debt_ratio > 0.5:
            return 70

        # Low leverage (safe)
        return 85

    df['balance_sheet_score'] = df.apply(calc_balance_sheet, axis=1)

    # === 4. ANALYST SENTIMENT SCORE (0-100) ===
    # Downgrade momentum is a red flag
    def calc_analyst_sentiment(row):
        if pd.isna(row['estimate_revision_direction']):
            return 50

        sentiment = float(row['estimate_revision_direction'])

        # Heavy downgrade momentum
        if sentiment < -50:
            return 30

        # Some downgrades
        if sentiment < 0:
            return 60

        # Upgrades
        return 80

    df['analyst_sentiment_score'] = df.apply(calc_analyst_sentiment, axis=1)

    # === 5. COMPOSITE TRAP RISK SCORE ===
    # Weighted average: earnings quality (40%), cash (30%), balance sheet (20%), analyst (10%)
    df['trap_risk_score'] = (
        df['earnings_quality_score'] * 0.40 +
        df['cash_quality_score'] * 0.30 +
        df['balance_sheet_score'] * 0.20 +
        df['analyst_sentiment_score'] * 0.10
    ).round(2)

    # Invert: Higher score = SAFER (no trap)
    # Lower score = DANGER ZONE (value trap)

    logger.info("Sample trap scores:")
    sample = df[df['trap_risk_score'].notna()].nlargest(5, 'trap_risk_score')[['symbol', 'trap_risk_score', 'earnings_quality_score', 'cash_quality_score']]
    logger.info(f"Safest stocks:\n{sample}")

    sample_trap = df[df['trap_risk_score'].notna()].nsmallest(5, 'trap_risk_score')[['symbol', 'trap_risk_score', 'earnings_quality_score', 'cash_quality_score']]
    logger.info(f"Highest risk traps:\n{sample_trap}")

    # === STORE IN DATABASE ===
    logger.info("Storing trap risk scores...")
    config = get_db_config()
    conn = psycopg2.connect(**config)
    cursor = conn.cursor()

    # Create table if not exists
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS value_trap_scores (
        symbol VARCHAR(10) PRIMARY KEY,
        trap_risk_score NUMERIC,
        earnings_quality_score NUMERIC,
        cash_quality_score NUMERIC,
        balance_sheet_score NUMERIC,
        analyst_sentiment_score NUMERIC,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )
    """)

    # Insert or update scores
    for idx, row in df[df['trap_risk_score'].notna()].iterrows():
        cursor.execute("""
        INSERT INTO value_trap_scores
        (symbol, trap_risk_score, earnings_quality_score, cash_quality_score, balance_sheet_score, analyst_sentiment_score)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (symbol) DO UPDATE SET
            trap_risk_score = EXCLUDED.trap_risk_score,
            earnings_quality_score = EXCLUDED.earnings_quality_score,
            cash_quality_score = EXCLUDED.cash_quality_score,
            balance_sheet_score = EXCLUDED.balance_sheet_score,
            analyst_sentiment_score = EXCLUDED.analyst_sentiment_score,
            updated_at = NOW()
        """, (
            row['symbol'],
            float(row['trap_risk_score']),
            float(row['earnings_quality_score']),
            float(row['cash_quality_score']),
            float(row['balance_sheet_score']),
            float(row['analyst_sentiment_score'])
        ))

    conn.commit()
    cursor.close()
    conn.close()

    inserted = df[df['trap_risk_score'].notna()].shape[0]
    logger.info(f" Stored {inserted} trap risk scores")

    return df

if __name__ == "__main__":
    calculate_trap_scores()
    logger.info("Value trap scoring complete!")
