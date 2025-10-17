#!/usr/bin/env python3
"""
Benchmark Index History Loader
Processes S&P 500 (SPY) and other benchmark daily prices and calculates returns.

This loader:
1. Fetches daily price data from price_daily table
2. Calculates daily returns and cumulative YTD returns
3. Stores processed data in benchmark_index_history table
4. Enables seasonality analysis with real market performance overlay

Output:
- benchmark_index_history table with daily returns and cumulative performance
"""

import json
import logging
import os
import sys
import time
from datetime import datetime
from decimal import Decimal

import psycopg2
from psycopg2.extras import execute_values

# Script metadata
SCRIPT_NAME = os.path.basename(__file__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s",
    stream=sys.stdout,
)

# Benchmark symbols to track (S&P 500 and alternatives)
BENCHMARK_SYMBOLS = ["SPY", "IVV", "VOO", "RSP", "^GSPC"]


def get_db_config():
    """Fetch database credentials from environment or use local config"""
    if os.environ.get("USE_LOCAL_DB") == "true" or not os.environ.get("DB_SECRET_ARN"):
        logging.info("Using local database configuration")
        return (
            os.environ.get("DB_USER", "postgres"),
            os.environ.get("DB_PASSWORD", "password"),
            os.environ.get("DB_HOST", "localhost"),
            int(os.environ.get("DB_PORT", "5432")),
            os.environ.get("DB_NAME", "stocks_algo"),
        )

    # AWS Secrets Manager fallback
    import boto3
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


def safe_float(value):
    """Safely convert value to float"""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def create_benchmark_table(conn):
    """Create benchmark_index_history table"""
    cursor = conn.cursor()

    logging.info("Creating benchmark_index_history table...")
    cursor.execute("""
        DROP TABLE IF EXISTS benchmark_index_history CASCADE;
    """)

    cursor.execute("""
        CREATE TABLE benchmark_index_history (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(50) NOT NULL,
            date DATE NOT NULL,
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            open DOUBLE PRECISION,
            high DOUBLE PRECISION,
            low DOUBLE PRECISION,
            close DOUBLE PRECISION NOT NULL,
            volume BIGINT,
            daily_return DOUBLE PRECISION,
            cumulative_year_return DOUBLE PRECISION,
            cumulative_month_return DOUBLE PRECISION,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, date)
        );
    """)

    # Create indexes for fast queries
    cursor.execute("""
        CREATE INDEX idx_benchmark_symbol ON benchmark_index_history(symbol);
    """)
    cursor.execute("""
        CREATE INDEX idx_benchmark_date ON benchmark_index_history(date);
    """)
    cursor.execute("""
        CREATE INDEX idx_benchmark_year_month ON benchmark_index_history(symbol, year, month);
    """)
    cursor.execute("""
        CREATE INDEX idx_benchmark_symbol_date ON benchmark_index_history(symbol, date DESC);
    """)

    conn.commit()
    cursor.close()
    logging.info("✅ benchmark_index_history table created")


def fetch_price_data(conn, symbol):
    """Fetch all available price data for a symbol"""
    cursor = conn.cursor()

    logging.info(f"Fetching price data for {symbol}...")
    cursor.execute("""
        SELECT
            date,
            open,
            high,
            low,
            close,
            volume
        FROM price_daily
        WHERE symbol = %s
        ORDER BY date ASC
    """, (symbol,))

    rows = cursor.fetchall()
    cursor.close()
    logging.info(f"  Found {len(rows)} trading days for {symbol}")

    return rows


def calculate_returns(price_data):
    """Calculate daily and cumulative returns"""
    records = []
    cumulative_return_by_year = {}
    cumulative_return_by_month = {}

    for date, open_price, high, low, close, volume in price_data:
        year = date.year
        month = date.month

        # Convert to float safely
        close_f = safe_float(close)
        open_f = safe_float(open_price)

        if close_f is None:
            continue

        # Calculate daily return
        daily_return = None
        if open_f is not None and open_f != 0:
            daily_return = ((close_f - open_f) / open_f) * 100

        # Calculate cumulative YTD return
        year_key = f"{year}-01-01"
        if year_key not in cumulative_return_by_year:
            cumulative_return_by_year[year_key] = 0

        if daily_return is not None:
            cumulative_return_by_year[year_key] += daily_return
        cumulative_year_return = cumulative_return_by_year[year_key]

        # Calculate cumulative month-to-date return
        month_key = f"{year}-{month:02d}-01"
        if month_key not in cumulative_return_by_month:
            cumulative_return_by_month[month_key] = 0

        if daily_return is not None:
            cumulative_return_by_month[month_key] += daily_return
        cumulative_month_return = cumulative_return_by_month[month_key]

        record = (
            date,
            year,
            month,
            safe_float(open_price),
            safe_float(high),
            safe_float(low),
            close_f,
            volume,
            daily_return,
            cumulative_year_return,
            cumulative_month_return,
        )
        records.append(record)

    return records


def store_benchmark_data(conn, symbol, records):
    """Store processed benchmark data in database"""
    if not records:
        logging.warning(f"No records to store for {symbol}")
        return 0

    cursor = conn.cursor()

    # Prepare data for insertion
    data_tuples = [(symbol,) + rec for rec in records]

    try:
        execute_values(
            cursor,
            """
            INSERT INTO benchmark_index_history
            (symbol, date, year, month, open, high, low, close, volume,
             daily_return, cumulative_year_return, cumulative_month_return)
            VALUES %s
            ON CONFLICT (symbol, date) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                daily_return = EXCLUDED.daily_return,
                cumulative_year_return = EXCLUDED.cumulative_year_return,
                cumulative_month_return = EXCLUDED.cumulative_month_return,
                updated_at = CURRENT_TIMESTAMP
            """,
            data_tuples,
        )
        conn.commit()
        logging.info(f"✅ Stored {len(records)} records for {symbol}")
        cursor.close()
        return len(records)

    except Exception as e:
        logging.error(f"❌ Error storing data for {symbol}: {e}")
        conn.rollback()
        cursor.close()
        return 0


def process_benchmark_symbol(conn, symbol):
    """Process a single benchmark symbol"""
    try:
        # Fetch price data
        price_data = fetch_price_data(conn, symbol)
        if not price_data:
            logging.warning(f"No price data found for {symbol}")
            return 0

        # Calculate returns
        records = calculate_returns(price_data)
        if not records:
            logging.warning(f"No records generated for {symbol}")
            return 0

        # Store in database
        count = store_benchmark_data(conn, symbol, records)
        return count

    except Exception as e:
        logging.error(f"❌ Error processing {symbol}: {e}")
        return 0


def get_summary_stats(conn, symbol):
    """Get summary statistics for a benchmark symbol"""
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            MIN(date) as first_date,
            MAX(date) as last_date,
            COUNT(*) as total_days,
            COUNT(DISTINCT year) as years_covered,
            ROUND(MAX(close)::numeric, 2) as max_price,
            ROUND(MIN(close)::numeric, 2) as min_price,
            ROUND(AVG(daily_return)::numeric, 3) as avg_daily_return,
            ROUND(MAX(cumulative_year_return)::numeric, 2) as max_ytd_return
        FROM benchmark_index_history
        WHERE symbol = %s
    """, (symbol,))

    row = cursor.fetchone()
    cursor.close()

    if row:
        return {
            'first_date': row[0],
            'last_date': row[1],
            'total_days': row[2],
            'years_covered': row[3],
            'max_price': row[4],
            'min_price': row[5],
            'avg_daily_return': row[6],
            'max_ytd_return': row[7],
        }
    return {}


def main():
    """Main execution function"""
    start_time = time.time()
    logging.info("=" * 80)
    logging.info("Benchmark Index History Loader - Starting")
    logging.info("=" * 80)

    # Connect to database
    user, pwd, host, port, db = get_db_config()
    try:
        conn = psycopg2.connect(host=host, port=port, user=user, password=pwd, dbname=db)
    except psycopg2.OperationalError as e:
        logging.error(f"❌ Database connection failed: {e}")
        sys.exit(1)

    # Step 1: Create table
    logging.info("\n[1/3] DATABASE TABLE")
    logging.info("-" * 80)
    create_benchmark_table(conn)

    # Step 2: Process benchmark symbols
    logging.info("\n[2/3] PROCESSING BENCHMARKS")
    logging.info("-" * 80)

    total_records = 0
    results = {}

    for symbol in BENCHMARK_SYMBOLS:
        count = process_benchmark_symbol(conn, symbol)
        total_records += count

        if count > 0:
            stats = get_summary_stats(conn, symbol)
            results[symbol] = {
                'records': count,
                'stats': stats,
            }
            logging.info(f"  {symbol}: {stats}")

    # Step 3: Summary
    logging.info("\n[3/3] SUMMARY")
    logging.info("-" * 80)

    for symbol, data in results.items():
        logging.info(f"✅ {symbol}: {data['records']} records")
        stats = data['stats']
        if stats:
            logging.info(f"   Date Range: {stats['first_date']} to {stats['last_date']}")
            logging.info(f"   Years Covered: {stats['years_covered']}")
            logging.info(f"   Price Range: ${stats['min_price']} - ${stats['max_price']}")
            logging.info(f"   Avg Daily Return: {stats['avg_daily_return']}%")

    # Cleanup
    conn.close()

    elapsed = time.time() - start_time
    logging.info("=" * 80)
    logging.info(f"✅ Benchmark Loader Complete!")
    logging.info(f"   Total Records: {total_records}")
    logging.info(f"   Symbols Processed: {len(results)}")
    logging.info(f"   Execution Time: {elapsed:.2f}s")
    logging.info("=" * 80)

    return total_records > 0


def lambda_handler(event, context):
    """AWS Lambda handler"""
    success = main()
    return {
        "statusCode": 200 if success else 500,
        "body": "Benchmark loader completed successfully" if success else "Benchmark loader failed"
    }


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
