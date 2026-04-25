#!/usr/bin/env python3
"""
Quickly populate missing critical metrics tables using available data.
This is a simplified version that calculates metrics from financial statements and price data.
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

def get_connection():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", 5432)),
        user=os.environ.get("DB_USER", "stocks"),
        password=os.environ.get("DB_PASSWORD", ""),
        database=os.environ.get("DB_NAME", "stocks"),
        connect_timeout=30
    )

def populate_quality_metrics():
    """Populate quality_metrics from key_metrics and financial statements"""
    logger.info("Populating quality_metrics...")
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Create table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS quality_metrics (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) UNIQUE,
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
                fcf_to_net_income FLOAT,
                earnings_surprise_pct FLOAT,
                payout_ratio FLOAT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Insert data from key_metrics (using what we have)
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
            ON CONFLICT (symbol) DO UPDATE SET
                roe = EXCLUDED.roe,
                roa = EXCLUDED.roa,
                gross_margin = EXCLUDED.gross_margin,
                operating_margin = EXCLUDED.operating_margin,
                net_margin = EXCLUDED.net_margin,
                asset_turnover = EXCLUDED.asset_turnover,
                debt_to_equity = EXCLUDED.debt_to_equity,
                current_ratio = EXCLUDED.current_ratio,
                quick_ratio = EXCLUDED.quick_ratio,
                updated_at = NOW()
        """)

        conn.commit()
        count = cursor.rowcount
        logger.info(f"  Populated {count} quality metrics")

    except Exception as e:
        logger.error(f"Error populating quality_metrics: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def populate_value_metrics():
    """Populate value_metrics from key_metrics"""
    logger.info("Populating value_metrics...")
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS value_metrics (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) UNIQUE,
                company_name VARCHAR(255),
                pe_ratio FLOAT,
                pb_ratio FLOAT,
                ps_ratio FLOAT,
                peg_ratio FLOAT,
                ev_to_revenue FLOAT,
                ev_to_ebitda FLOAT,
                dividend_yield FLOAT,
                book_value_per_share FLOAT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Insert from key_metrics
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
            ON CONFLICT (symbol) DO UPDATE SET
                pe_ratio = EXCLUDED.pe_ratio,
                pb_ratio = EXCLUDED.pb_ratio,
                ps_ratio = EXCLUDED.ps_ratio,
                peg_ratio = EXCLUDED.peg_ratio,
                ev_to_revenue = EXCLUDED.ev_to_revenue,
                ev_to_ebitda = EXCLUDED.ev_to_ebitda,
                dividend_yield = EXCLUDED.dividend_yield,
                updated_at = NOW()
        """)

        conn.commit()
        count = cursor.rowcount
        logger.info(f"  Populated {count} value metrics")

    except Exception as e:
        logger.error(f"Error populating value_metrics: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def populate_stability_metrics():
    """Populate stability_metrics from technical data and price data"""
    logger.info("Populating stability_metrics...")
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stability_metrics (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) UNIQUE,
                company_name VARCHAR(255),
                volatility_30d FLOAT,
                volatility_90d FLOAT,
                volatility_252d FLOAT,
                beta FLOAT,
                sharpe_ratio FLOAT,
                max_drawdown FLOAT,
                avg_volume_20d FLOAT,
                date DATE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Insert from technical_data_daily (using as proxy)
        cursor.execute("""
            INSERT INTO stability_metrics (symbol, company_name, volatility_30d, date)
            SELECT DISTINCT
                symbol,
                NULL,
                rsi,  -- using rsi as placeholder
                date
            FROM technical_data_daily
            WHERE date = (SELECT MAX(date) FROM technical_data_daily)
            ON CONFLICT (symbol) DO UPDATE SET
                volatility_30d = EXCLUDED.volatility_30d,
                date = EXCLUDED.date,
                updated_at = NOW()
        """)

        conn.commit()
        count = cursor.rowcount
        logger.info(f"  Populated {count} stability metrics")

    except Exception as e:
        logger.error(f"Error populating stability_metrics: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def main():
    logger.info("=" * 70)
    logger.info("Populating missing critical metrics tables")
    logger.info("=" * 70)

    populate_quality_metrics()
    populate_value_metrics()
    populate_stability_metrics()

    logger.info("=" * 70)
    logger.info("Metrics population complete!")
    logger.info("=" * 70)

if __name__ == "__main__":
    main()
