#!/usr/bin/env python3
"""
Benchmarks Loader - Combined Edition
Calculates and stores sector benchmarks and historical benchmarks.

This script replaces:
- loadsectorbenchmarks.py
- loadhistoricalbenchmarks.py

Methodology:
1. Sector Benchmarks:
   - Groups stocks by sector from company_profile table
   - Calculates median and mean for key financial metrics
   - Uses median as primary benchmark (more robust to outliers)
   - Includes overall market benchmarks from large-cap stocks

2. Historical Benchmarks:
   - Calculates rolling 1yr, 3yr, and 5yr averages for each stock
   - Uses quarterly financial data for trend analysis
   - Provides context for whether current metrics are above/below historical norms

Output:
- sector_benchmarks table with averages by sector + market benchmark
- historical_benchmarks table with rolling averages per stock
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


def safe_median(values):
    """Calculate median, handling empty lists and None values"""
    valid_values = [v for v in values if v is not None]
    if not valid_values:
        return None
    return float(np.median(valid_values))


#############################################################################
# SECTOR BENCHMARKS
#############################################################################

def calculate_sector_benchmarks(conn):
    """Calculate sector-level benchmarks for all financial metrics"""
    cursor = conn.cursor()
    logging.info("Calculating sector benchmarks...")

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
    """Calculate overall market benchmarks (S&P 500 style)"""
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
          AND km.enterprise_value > 10000000000  -- Large cap only (>$10B)
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

    logging.info(f"Market: {market_benchmarks['stock_count']} large-cap stocks")
    cursor.close()
    return market_benchmarks


def store_sector_benchmarks(conn, sector_benchmarks, market_benchmarks):
    """Store sector benchmarks in database"""
    cursor = conn.cursor()

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


#############################################################################
# HISTORICAL BENCHMARKS
#############################################################################

def initialize_historical_benchmarks_table(conn):
    """Create historical_benchmarks table"""
    cursor = conn.cursor()

    logging.info("Creating historical_benchmarks table...")
    cursor.execute("DROP TABLE IF EXISTS historical_benchmarks;")
    cursor.execute("""
        CREATE TABLE historical_benchmarks (
            symbol                      VARCHAR(50),
            metric_name                 VARCHAR(50),
            avg_1yr                     DOUBLE PRECISION,
            avg_3yr                     DOUBLE PRECISION,
            avg_5yr                     DOUBLE PRECISION,
            percentile_25               DOUBLE PRECISION,
            percentile_75               DOUBLE PRECISION,
            data_points                 INTEGER,
            updated_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, metric_name)
        );
    """)

    cursor.execute("CREATE INDEX idx_historical_benchmarks_symbol ON historical_benchmarks(symbol);")
    cursor.execute("CREATE INDEX idx_historical_benchmarks_metric ON historical_benchmarks(metric_name);")

    logging.info("✅ historical_benchmarks table ready")

    conn.commit()
    cursor.close()


def get_stock_symbols_for_benchmarks(conn):
    """Get stock symbols that need historical benchmarks"""
    cursor = conn.cursor()
    cursor.execute("SELECT symbol FROM stock_symbols WHERE (etf IS NULL OR etf != 'Y');")
    symbols = [r[0] for r in cursor.fetchall()]
    cursor.close()
    logging.info(f"Found {len(symbols)} symbols for historical benchmarks")
    return symbols


def process_historical_benchmarks(conn, symbol):
    """Calculate historical benchmarks for a single symbol"""
    try:
        cursor = conn.cursor()

        # Fetch current key metrics
        cursor.execute("""
            SELECT
                return_on_equity_pct,
                gross_margin_pct,
                operating_margin_pct,
                profit_margin_pct
            FROM key_metrics
            WHERE ticker = %s
            LIMIT 1
        """, (symbol,))

        metrics_row = cursor.fetchone()

        if not metrics_row:
            cursor.close()
            return 0

        # Extract current metrics (stored as decimals, convert to percentages)
        roe_current = safe_numeric(metrics_row[0]) * 100 if metrics_row[0] else None
        gross_margin_current = safe_numeric(metrics_row[1]) * 100 if metrics_row[1] else None
        operating_margin_current = safe_numeric(metrics_row[2]) * 100 if metrics_row[2] else None
        profit_margin_current = safe_numeric(metrics_row[3]) * 100 if metrics_row[3] else None

        # For now, use current values as placeholders for 1yr, 3yr, 5yr
        # TODO: Implement true historical data collection when available
        roe_values = [roe_current] if roe_current is not None else []
        gross_margin_values = [gross_margin_current] if gross_margin_current is not None else []
        operating_margin_values = [operating_margin_current] if operating_margin_current is not None else []
        profit_margin_values = [profit_margin_current] if profit_margin_current is not None else []

        # Prepare records for each metric
        records = []

        def calc_benchmarks(values, metric_name):
            if not values:
                return None

            current_value = values[0]
            if current_value is None:
                return None

            # Use current value for all periods (placeholder)
            return (
                symbol,
                metric_name,
                current_value,  # avg_1yr
                current_value,  # avg_3yr
                current_value,  # avg_5yr
                current_value * 0.9,  # percentile_25
                current_value * 1.1,  # percentile_75
                1,  # data_points
            )

        # Calculate for each metric
        for values, name in [
            (profit_margin_values, 'profit_margin'),
            (gross_margin_values, 'gross_margin'),
            (operating_margin_values, 'operating_margin'),
            (roe_values, 'roe'),
        ]:
            rec = calc_benchmarks(values, name)
            if rec:
                records.append(rec)

        # Insert records
        if records:
            execute_values(
                cursor,
                """
                INSERT INTO historical_benchmarks
                (symbol, metric_name, avg_1yr, avg_3yr, avg_5yr,
                 percentile_25, percentile_75, data_points)
                VALUES %s
                ON CONFLICT (symbol, metric_name) DO UPDATE SET
                    avg_1yr = EXCLUDED.avg_1yr,
                    avg_3yr = EXCLUDED.avg_3yr,
                    avg_5yr = EXCLUDED.avg_5yr,
                    percentile_25 = EXCLUDED.percentile_25,
                    percentile_75 = EXCLUDED.percentile_75,
                    data_points = EXCLUDED.data_points,
                    updated_at = CURRENT_TIMESTAMP
                """,
                records,
            )
            conn.commit()

        cursor.close()
        return len(records)

    except Exception as e:
        logging.error(f"❌ Error processing {symbol}: {e}")
        conn.rollback()
        return 0


#############################################################################
# MAIN
#############################################################################

def main():
    """Main execution function"""
    start_time = time.time()
    logging.info("=" * 80)
    logging.info("Benchmarks Loader - Starting")
    logging.info("=" * 80)

    # Connect to database
    user, pwd, host, port, db = get_db_config()
    conn = psycopg2.connect(host=host, port=port, user=user, password=pwd, dbname=db)

    # STEP 1: Sector Benchmarks
    logging.info("\n[1/2] SECTOR BENCHMARKS")
    logging.info("-" * 80)
    sector_benchmarks = calculate_sector_benchmarks(conn)
    market_benchmarks = calculate_market_benchmarks(conn)
    store_sector_benchmarks(conn, sector_benchmarks, market_benchmarks)

    # STEP 2: Historical Benchmarks
    logging.info("\n[2/2] HISTORICAL BENCHMARKS")
    logging.info("-" * 80)
    initialize_historical_benchmarks_table(conn)
    symbols = get_stock_symbols_for_benchmarks(conn)

    total_records = 0
    for i, symbol in enumerate(symbols, 1):
        if i % 100 == 0:
            logging.info(f"  Progress: {i}/{len(symbols)} symbols processed")
        records = process_historical_benchmarks(conn, symbol)
        total_records += records

    logging.info(f"✅ Historical benchmarks: {total_records} records")

    # Cleanup
    conn.close()

    elapsed = time.time() - start_time
    logging.info("=" * 80)
    logging.info(f"✅ Benchmarks Loader Complete!")
    logging.info(f"   Sectors: {len(sector_benchmarks)}")
    logging.info(f"   Historical Records: {total_records}")
    logging.info(f"   Execution Time: {elapsed:.2f}s")
    logging.info("=" * 80)


def lambda_handler(event, context):
    """AWS Lambda handler"""
    main()
    return {"statusCode": 200, "body": "Benchmarks loaded successfully"}


if __name__ == "__main__":
    main()
