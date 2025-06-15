#!/usr/bin/env python3 
import sys
import time
import logging
import json
import os
import gc
import psutil
import warnings
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from functools import partial

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
import boto3
import numpy as np
import pandas as pd

# Suppress warnings for performance
warnings.simplefilter(action='ignore', category=FutureWarning)
warnings.simplefilter(action='ignore', category=pd.errors.PerformanceWarning)

# -------------------------------
# Script metadata & logging setup 
# -------------------------------
SCRIPT_NAME = "loadtechnicalsdaily.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

logging.info("✅ Using Pure NumPy/Pandas Implementation - No TA-Lib Dependencies!")

# -------------------------------
# Memory-logging helper (RSS in MB) - Cross-platform compatible
# -------------------------------
def get_rss_mb():
    """Get RSS memory usage in MB - works on all platforms"""
    return psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024

def log_mem(stage: str):
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")

def validate_prerequisites(cur):
    """Validate that prerequisites for loading technical data are met - FIXED VERSION"""
    try:
        logging.info("🔍 Step 1: Checking if price_daily table exists...")
        
        # Check if price_daily table exists and has data
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'price_daily'
            ) as table_exists
        """)
        result = cur.fetchone()
        price_table_exists = result['table_exists']
        logging.info(f"📊 price_daily table exists: {price_table_exists}")
        
        if not price_table_exists:
            logging.error("❌ price_daily table does not exist. Technical data requires price data.")
            logging.error("💡 Hint: Run the price data loader first (pricedaily-loader) to populate price_daily table")
            return False
        
        logging.info("🔍 Step 2: Checking if price_daily table has data...")
        
        # Check total number of rows first
        cur.execute("SELECT COUNT(*) as total_rows FROM price_daily")
        result = cur.fetchone()
        total_rows = result['total_rows']
        logging.info(f"📊 Total rows in price_daily: {total_rows}")
        
        if total_rows == 0:
            logging.error("❌ price_daily table exists but is empty (0 rows)")
            logging.error("💡 Hint: Run the price data loader first (pricedaily-loader) to populate price_daily table")
            return False
        
        # Check if we have price data for symbols
        logging.info("🔍 Step 3: Counting distinct symbols in price_daily...")
        cur.execute("SELECT COUNT(DISTINCT symbol) as symbol_count FROM price_daily")
        result = cur.fetchone()
        price_symbol_count = result['symbol_count'] if result else 0
        logging.info(f"📊 Distinct symbols in price_daily: {price_symbol_count}")
        
        if price_symbol_count == 0:
            logging.error("❌ No distinct symbols found in price_daily table")
            logging.error("💡 This is unusual - table has rows but no distinct symbols")
            return False
        
        logging.info(f"✅ Prerequisites met: price_daily table exists with {price_symbol_count} symbols")
        return True
        
    except Exception as e:
        logging.error(f"❌ Exception type: {type(e).__name__}")
        logging.error(f"❌ Exception details: {repr(e)}")
        logging.error(f"❌ Full traceback: {str(e)}")
        import traceback
        logging.error(f"❌ Full traceback: {''.join(traceback.format_exc())}")
        return False

def get_db_config():
    """Get database configuration from AWS Secrets Manager"""
    try:
        # Get the secret ARN from environment variable
        secret_arn = os.environ.get('DB_SECRET_ARN')
        if not secret_arn:
            raise ValueError("DB_SECRET_ARN environment variable not set")
        
        # Create a Secrets Manager client
        session = boto3.session.Session()
        client = session.client(service_name='secretsmanager', region_name='us-east-1')
        
        # Get the secret value
        response = client.get_secret_value(SecretId=secret_arn)
        secret = json.loads(response['SecretString'])
        
        return {
            'host': secret['host'],
            'port': secret['port'],
            'dbname': secret['dbname'],
            'user': secret['username'],
            'password': secret['password']
        }
    except Exception as e:
        logging.error(f"❌ Failed to get database configuration: {e}")
        raise

if __name__ == "__main__":
    try:
        log_mem("startup")
        logging.info(f"🚀 Starting {SCRIPT_NAME}")

        # Connect to DB
        cfg = get_db_config()
        conn = psycopg2.connect(
            host=cfg["host"], port=cfg["port"],
            user=cfg["user"], password=cfg["password"],
            dbname=cfg["dbname"]
        )
        conn.autocommit = False
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Just validate prerequisites - don't actually load data yet
        logging.info("🔍 Validating prerequisites...")
        if not validate_prerequisites(cur):
            logging.error("❌ Prerequisites not met for loading technical data")
            sys.exit(0)
        
        logging.info("✅ Prerequisites validation passed!")
        logging.info("💡 Technical data loading logic will be implemented next")
        
        # Close connections
        cur.close()
        conn.close()
        
        logging.info("🏁 loadtechnicalsdaily.py finished")
        logging.info("✅ Process completed successfully")
        logging.info(f"🏁 {SCRIPT_NAME} finished with exit code 0")
        
    except Exception as e:
        logging.error(f"❌ Fatal error in main: {e}")
        import traceback
        logging.error(f"❌ Full traceback: {''.join(traceback.format_exc())}")
        sys.exit(1)
