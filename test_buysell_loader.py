#!/usr/bin/env python3
"""
Test script to diagnose buy/sell loader issues
"""
import json
import logging
import os
import sys
from datetime import datetime

import boto3
import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

def test_database_connection():
    """Test database connection and check required tables"""
    try:
        # Get database credentials from AWS Secrets Manager
        SECRET_ARN = os.environ.get("DB_SECRET_ARN")
        if not SECRET_ARN:
            logging.error("DB_SECRET_ARN environment variable not set")
            return False

        sm_client = boto3.client("secretsmanager")
        secret_resp = sm_client.get_secret_value(SecretId=SECRET_ARN)
        creds = json.loads(secret_resp["SecretString"])

        DB_CONFIG = {
            "host": creds["host"],
            "port": int(creds.get("port", 5432)),
            "user": creds["username"],
            "password": creds["password"],
            "dbname": creds["dbname"],
        }

        logging.info("Testing database connection...")
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Test connection
        cur.execute("SELECT version()")
        version = cur.fetchone()
        logging.info(f"Database connection successful: {version['version']}")

        # Check required tables
        required_tables = [
            'stock_symbols',
            'price_daily',
            'technical_data_daily',
            'buy_sell_daily'
        ]

        for table in required_tables:
            cur.execute("""
                SELECT EXISTS (
                   SELECT FROM information_schema.tables
                   WHERE table_schema = 'public'
                   AND table_name = %s
                );
            """, (table,))

            exists = cur.fetchone()['exists']
            logging.info(f"Table '{table}': {'EXISTS' if exists else 'MISSING'}")

            if exists and table == 'stock_symbols':
                # Check for active symbols
                cur.execute("SELECT COUNT(*) as count FROM stock_symbols WHERE status = 'active'")
                count = cur.fetchone()['count']
                logging.info(f"Active symbols count: {count}")

            elif exists and table == 'price_daily':
                # Check latest price data
                cur.execute("SELECT MAX(date) as latest_date, COUNT(DISTINCT symbol) as symbol_count FROM price_daily")
                result = cur.fetchone()
                logging.info(f"Latest price data: {result['latest_date']}, Symbol count: {result['symbol_count']}")

            elif exists and table == 'technical_data_daily':
                # Check latest technical data
                cur.execute("SELECT MAX(date) as latest_date, COUNT(DISTINCT symbol) as symbol_count FROM technical_data_daily")
                result = cur.fetchone()
                logging.info(f"Latest technical data: {result['latest_date']}, Symbol count: {result['symbol_count']}")

            elif exists and table == 'buy_sell_daily':
                # Check existing signals
                cur.execute("SELECT MAX(date) as latest_date, COUNT(*) as signal_count FROM buy_sell_daily")
                result = cur.fetchone()
                logging.info(f"Latest buy/sell signals: {result['latest_date']}, Signal count: {result['signal_count']}")

        # Test specific query that the loader uses
        logging.info("Testing loader query...")
        cur.execute("""
            SELECT DISTINCT symbol
            FROM stock_symbols
            WHERE status = 'active'
            LIMIT 1
        """)
        test_symbols = cur.fetchall()

        if test_symbols:
            test_symbol = test_symbols[0]['symbol']
            logging.info(f"Testing with symbol: {test_symbol}")

            # Test the main query from the loader
            cur.execute("""
                SELECT
                    p.symbol, p.date, p.open, p.high, p.low, p.close, p.adj_close, p.volume,
                    t.rsi, t.macd, t.signal_line, t.macd_histogram, t.bb_upper, t.bb_lower,
                    t.stoch_k, t.stoch_d, t.williams_r, t.cci, t.adx
                FROM price_daily p
                LEFT JOIN technical_data_daily t ON p.symbol = t.symbol AND p.date = t.date
                WHERE p.symbol = %s
                ORDER BY p.date DESC
                LIMIT 5
            """, (test_symbol,))

            test_data = cur.fetchall()
            logging.info(f"Sample data rows: {len(test_data)}")

            for row in test_data[:2]:  # Show first 2 rows
                logging.info(f"Sample: {test_symbol} {row['date']} close=${row['close']} rsi={row['rsi']} macd={row['macd']}")

        cur.close()
        conn.close()

        logging.info("Database test completed successfully")
        return True

    except Exception as e:
        logging.error(f"Database test failed: {e}")
        return False

def test_environment():
    """Test environment variables and AWS access"""
    logging.info("Testing environment...")

    required_env_vars = ['DB_SECRET_ARN']
    for var in required_env_vars:
        value = os.environ.get(var)
        if value:
            logging.info(f"{var}: Set (length: {len(value)})")
        else:
            logging.error(f"{var}: NOT SET")

    # Test AWS access
    try:
        boto3.client("secretsmanager").get_caller_identity()
        logging.info("AWS access: OK")
    except Exception as e:
        logging.error(f"AWS access failed: {e}")

if __name__ == "__main__":
    logging.info("=== Buy/Sell Loader Diagnostic Test ===")

    test_environment()
    test_database_connection()

    logging.info("=== Test Complete ===")