#!/usr/bin/env python3
# Trigger deployment - 2025-10-16 14:33 - Force rebuild: 20251016_143400 - Populate sector benchmarks to AWS
"""
Sector Benchmarks Loader
Calculates sector-level averages for financial metrics to provide context-specific benchmarks

Methodology:
- Groups stocks by sector from stock_symbols table
- Calculates median and mean for key financial metrics
- Uses median as primary benchmark (more robust to outliers)
- Stores sector benchmarks for quality, valuation, and profitability metrics

Output:
- sector_benchmarks table with averages by sector
- Used for comparative analysis in stock detail pages
"""

import json
import logging
import os
import sys
import time
from datetime import datetime
from decimal import Decimal

import boto3
import numpy as np
import psycopg2
from psycopg2.extras import execute_values

# Script metadata
SCRIPT_NAME = os.path.basename(__file__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s",
    stream=sys.stdout,
)


def get_db_config():
    """Fetch database credentials from AWS Secrets Manager or use local config"""
    if os.environ.get("USE_LOCAL_DB") == "true" or not os.environ.get("DB_SECRET_ARN"):
        logging.info("Using local database configuration")
        return (
            os.environ.get("DB_USER", "postgres"),
            os.environ.get("DB_PASSWORD", "password"),
            os.environ.get("DB_HOST", "localhost"),
            int(os.environ.get("DB_PORT", "5432")),
            os.environ.get("DB_NAME", "stocks"),
        )

    client = boto3.client("secretsmanager")
    resp = client.get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])
    sec = json.loads(resp["SecretString"])
    return (
        sec["username"],
        sec["password"],
        sec["host"],
        int(sec["port"]),
        sec["dbname"],
    )


def safe_numeric(value):
    """Safely convert value to float, handling None, NaN, and Decimal"""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        if np.isnan(value) or np.isinf(value):
            return None
        return float(value)
    return None


def calculate_sector_benchmarks(conn):
    """
    Calculate sector-level benchmarks for all financial metrics

    Returns dictionary with sector benchmarks:
    {
        'Technology': {
            'roe': 23.5,
            'gross_margin': 65.2,
            'operating_margin': 28.3,
            ...
        }
    }
    """
    cursor = conn.cursor()

    logging.info("Calculating sector benchmarks...")

    # Query to calculate sector averages for profitability metrics
    cursor.execute("""
        SELECT
            cp.sector,
            -- Profitability metrics (convert from decimal to percentage)
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.return_on_equity_pct) * 100 as median_roe,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.return_on_assets_pct) * 100 as median_roa,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.gross_margin_pct) * 100 as median_gross_margin,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.operating_margin_pct) * 100 as median_operating_margin,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.profit_margin_pct) * 100 as median_profit_margin,

            -- Valuation metrics
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.trailing_pe) as median_pe,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.price_to_book) as median_pb,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.ev_to_ebitda) as median_ev_ebitda,

            -- Financial strength
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.debt_to_equity) as median_debt_to_equity,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.current_ratio) as median_current_ratio,

            -- Count of stocks in sector
            COUNT(*) as stock_count
        FROM company_profile cp
        JOIN key_metrics km ON cp.ticker = km.ticker
        LEFT JOIN stock_symbols ss ON cp.ticker = ss.symbol
        WHERE cp.sector IS NOT NULL
          AND cp.sector != ''
          AND (ss.etf IS NULL OR ss.etf != 'Y')
        GROUP BY cp.sector
        HAVING COUNT(*) >= 5  -- Only sectors with at least 5 stocks
        ORDER BY cp.sector
    """)

    sector_data = cursor.fetchall()
    logging.info(f"Found {len(sector_data)} sectors with sufficient data")

    benchmarks = {}
    for row in sector_data:
        sector = row[0]
        benchmarks[sector] = {
            'roe': safe_numeric(row[1]),
            'roa': safe_numeric(row[2]),
            'gross_margin': safe_numeric(row[3]),
            'operating_margin': safe_numeric(row[4]),
            'profit_margin': safe_numeric(row[5]),
            'pe_ratio': safe_numeric(row[6]),
            'price_to_book': safe_numeric(row[7]),
            'ev_to_ebitda': safe_numeric(row[8]),
            'debt_to_equity': safe_numeric(row[9]),
            'current_ratio': safe_numeric(row[10]),
            'stock_count': int(row[11]) if row[11] else 0,
        }

        roe = benchmarks[sector]['roe']
        pe = benchmarks[sector]['pe_ratio']
        roe_str = f"{roe:.1f}" if roe is not None else "N/A"
        pe_str = f"{pe:.1f}" if pe is not None else "N/A"
        logging.info(
            f"  {sector}: {benchmarks[sector]['stock_count']} stocks, "
            f"ROE={roe_str}%, P/E={pe_str}"
        )

    cursor.close()
    return benchmarks


def calculate_market_benchmarks(conn):
    """
    Calculate overall market benchmarks (S&P 500 style)
    Uses all large-cap stocks (market cap > $10B)
    """
    cursor = conn.cursor()

    logging.info("Calculating market benchmarks...")

    cursor.execute("""
        SELECT
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.return_on_equity_pct) * 100 as median_roe,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.return_on_assets_pct) * 100 as median_roa,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.gross_margin_pct) * 100 as median_gross_margin,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.operating_margin_pct) * 100 as median_operating_margin,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.profit_margin_pct) * 100 as median_profit_margin,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.trailing_pe) as median_pe,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.price_to_book) as median_pb,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.ev_to_ebitda) as median_ev_ebitda,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.debt_to_equity) as median_debt_to_equity,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY km.current_ratio) as median_current_ratio,
            COUNT(*) as stock_count
        FROM key_metrics km
        LEFT JOIN stock_symbols ss ON km.ticker = ss.symbol
        WHERE (ss.etf IS NULL OR ss.etf != 'Y')
          AND km.enterprise_value > 10000000000  -- Large cap only (>$10B enterprise value)
    """)

    row = cursor.fetchone()

    market_benchmarks = {
        'roe': safe_numeric(row[0]),
        'roa': safe_numeric(row[1]),
        'gross_margin': safe_numeric(row[2]),
        'operating_margin': safe_numeric(row[3]),
        'profit_margin': safe_numeric(row[4]),
        'pe_ratio': safe_numeric(row[5]),
        'price_to_book': safe_numeric(row[6]),
        'ev_to_ebitda': safe_numeric(row[7]),
        'debt_to_equity': safe_numeric(row[8]),
        'current_ratio': safe_numeric(row[9]),
        'stock_count': int(row[10]) if row[10] else 0,
    }

    mkt_roe = market_benchmarks['roe']
    mkt_pe = market_benchmarks['pe_ratio']
    mkt_roe_str = f"{mkt_roe:.1f}" if mkt_roe is not None else "N/A"
    mkt_pe_str = f"{mkt_pe:.1f}" if mkt_pe is not None else "N/A"
    logging.info(
        f"Market benchmarks calculated from {market_benchmarks['stock_count']} large-cap stocks"
    )
    logging.info(
        f"  Market ROE={mkt_roe_str}%, P/E={mkt_pe_str}"
    )

    cursor.close()
    return market_benchmarks


def store_benchmarks(conn, sector_benchmarks, market_benchmarks):
    """Store calculated benchmarks in database"""
    cursor = conn.cursor()

    # Create table
    logging.info("Creating sector_benchmarks table...")
    cursor.execute("DROP TABLE IF EXISTS sector_benchmarks;")
    cursor.execute("""
        CREATE TABLE sector_benchmarks (
            sector                      VARCHAR(100) PRIMARY KEY,
            roe                         DOUBLE PRECISION,
            roa                         DOUBLE PRECISION,
            gross_margin                DOUBLE PRECISION,
            operating_margin            DOUBLE PRECISION,
            profit_margin               DOUBLE PRECISION,
            pe_ratio                    DOUBLE PRECISION,
            price_to_book               DOUBLE PRECISION,
            ev_to_ebitda                DOUBLE PRECISION,
            debt_to_equity              DOUBLE PRECISION,
            current_ratio               DOUBLE PRECISION,
            stock_count                 INTEGER,
            updated_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Insert sector benchmarks
    sector_records = []
    for sector, metrics in sector_benchmarks.items():
        sector_records.append((
            sector,
            metrics['roe'],
            metrics['roa'],
            metrics['gross_margin'],
            metrics['operating_margin'],
            metrics['profit_margin'],
            metrics['pe_ratio'],
            metrics['price_to_book'],
            metrics['ev_to_ebitda'],
            metrics['debt_to_equity'],
            metrics['current_ratio'],
            metrics['stock_count'],
        ))

    if sector_records:
        execute_values(
            cursor,
            """
            INSERT INTO sector_benchmarks (
                sector, roe, roa, gross_margin, operating_margin, profit_margin,
                pe_ratio, price_to_book, ev_to_ebitda, debt_to_equity,
                current_ratio, stock_count
            ) VALUES %s
            """,
            sector_records,
        )
        logging.info(f"✅ Inserted {len(sector_records)} sector benchmarks")

    # Insert market benchmark with special sector name 'MARKET'
    cursor.execute("""
        INSERT INTO sector_benchmarks (
            sector, roe, roa, gross_margin, operating_margin, profit_margin,
            pe_ratio, price_to_book, ev_to_ebitda, debt_to_equity,
            current_ratio, stock_count
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        'MARKET',
        market_benchmarks['roe'],
        market_benchmarks['roa'],
        market_benchmarks['gross_margin'],
        market_benchmarks['operating_margin'],
        market_benchmarks['profit_margin'],
        market_benchmarks['pe_ratio'],
        market_benchmarks['price_to_book'],
        market_benchmarks['ev_to_ebitda'],
        market_benchmarks['debt_to_equity'],
        market_benchmarks['current_ratio'],
        market_benchmarks['stock_count'],
    ))

    logging.info("✅ Inserted market benchmark")

    # Create index
    cursor.execute("CREATE INDEX idx_sector_benchmarks_sector ON sector_benchmarks(sector);")

    conn.commit()
    cursor.close()


def main():
    """Main execution function"""
    start_time = time.time()
    logging.info("=" * 80)
    logging.info("Sector Benchmarks Loader - Starting")
    logging.info("=" * 80)

    # Connect to database
    user, pwd, host, port, db = get_db_config()
    conn = psycopg2.connect(host=host, port=port, user=user, password=pwd, dbname=db)

    # Calculate benchmarks
    sector_benchmarks = calculate_sector_benchmarks(conn)
    market_benchmarks = calculate_market_benchmarks(conn)

    # Store in database
    store_benchmarks(conn, sector_benchmarks, market_benchmarks)

    # Record script execution
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS last_updated (
            script_name VARCHAR(255) PRIMARY KEY,
            last_run TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cursor.execute("""
        INSERT INTO last_updated (script_name, last_run)
        VALUES (%s, CURRENT_TIMESTAMP)
        ON CONFLICT (script_name) DO UPDATE
        SET last_run = CURRENT_TIMESTAMP;
    """, (SCRIPT_NAME,))
    conn.commit()
    cursor.close()

    # Cleanup
    conn.close()

    elapsed = time.time() - start_time
    logging.info("=" * 80)
    logging.info(f"✅ Sector Benchmarks Loader Complete!")
    logging.info(f"   Sectors: {len(sector_benchmarks)}")
    logging.info(f"   Execution Time: {elapsed:.2f}s")
    logging.info("=" * 80)


def lambda_handler(event, context):
    """AWS Lambda handler"""
    main()
    return {"statusCode": 200, "body": "Sector benchmarks loaded successfully"}


if __name__ == "__main__":
    main()
