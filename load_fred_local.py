#!/usr/bin/env python3
"""
Local FRED Economic Data Loader
Separate from AWS loader, designed for local development
"""

import json
import logging
import os
import sys
from datetime import datetime

import pandas as pd
import psycopg2
from fredapi import Fred
from psycopg2.extras import execute_values

# Setup logging
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger()

# Local configuration
FRED_API_KEY = "4f87c213871ed1a9508c06957fa9b577"
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "user": "postgres", 
    "password": "password",
    "dbname": "stocks"
}

def main():
    """Load FRED economic data into local database"""
    logger.info("🏃 Starting Local FRED Economic Data Loader...")
    logger.info(f"📊 Target Database: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}")
    
    try:
        # 1) Connect to database
        logger.info("🔌 Connecting to local database...")
        conn = psycopg2.connect(
            host=DB_CONFIG["host"],
            port=DB_CONFIG["port"],
            dbname=DB_CONFIG["dbname"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            sslmode="disable"  # Local connection
        )
        cur = conn.cursor()
        logger.info("✅ Database connection established")

        # 2) Ensure table exists (matches AWS loader exactly)
        logger.info("📋 Creating/verifying economic_data table...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS economic_data (
                series_id TEXT NOT NULL,
                date       DATE NOT NULL,
                value      DOUBLE PRECISION,
                PRIMARY KEY (series_id, date)
            );
        """)
        conn.commit()
        logger.info("✅ Table structure verified")

        # 3) FRED Series (same as AWS loader)
        series_ids = [
            # U.S. Output & Demand
            "GDPC1",
            "PCECC96", 
            "GPDI",
            "GCEC1",
            "EXPGSC1",
            "IMPGSC1",
            # U.S. Labor Market
            "UNRATE",
            "PAYEMS",
            "CIVPART",
            "CES0500000003",
            "AWHAE", 
            "JTSJOL",
            "ICSA",
            "OPHNFB",
            "U6RATE",
            # U.S. Inflation & Prices
            "CPIAUCSL",
            "CPILFESL",
            "PCEPI", 
            "PCEPILFE",
            "PPIACO",
            "MICH",
            "T5YIFR",
            # U.S. Financial & Monetary
            "FEDFUNDS",
            "DGS2",
            "DGS10",
            "T10Y2Y",
            "MORTGAGE30US",
            "BAA",
            "AAA",
            "SP500",
            "VIXCLS",
            # U.S. Business & Manufacturing
            "INDPRO",
            "NAPM",
            "UMCSENT",
            "HOUST",
            "PERMIT",
            "RETAILMNSA",
            "NEWORDER",
            "DRTSCILM",
            # U.S. International Trade
            "BOPGSTB",
            "EXCHUS",
            "RRVRUSQ156N",
            "USHVAC",
        ]

        logger.info(f"📈 Initializing FRED API client...")
        fred = Fred(api_key=FRED_API_KEY)
        logger.info(f"✅ FRED API ready - will fetch {len(series_ids)} series")

        # 4) Fetch & upsert each series
        successful_loads = 0
        total_records = 0
        
        for i, series_id in enumerate(series_ids, 1):
            logger.info(f"📊 [{i}/{len(series_ids)}] Fetching {series_id}...")
            try:
                # Fetch time series data
                ts = fred.get_series(series_id)
                
                if ts is None or ts.empty:
                    logger.warning(f"⚠️  No data returned for {series_id}")
                    continue
                
                # Convert to records for database insert
                records = []
                for date, value in ts.items():
                    if pd.notna(value):  # Skip NaN values
                        records.append((series_id, date.date(), float(value)))
                
                if not records:
                    logger.warning(f"⚠️  No valid records for {series_id}")
                    continue
                
                # Upsert to database
                execute_values(
                    cur,
                    """
                    INSERT INTO economic_data (series_id, date, value)
                    VALUES %s
                    ON CONFLICT (series_id, date) 
                    DO UPDATE SET value = EXCLUDED.value
                    """,
                    records,
                    page_size=1000
                )
                
                conn.commit()
                successful_loads += 1
                total_records += len(records)
                logger.info(f"✅ {series_id}: {len(records)} records loaded")
                
            except Exception as e:
                logger.error(f"❌ Failed to fetch {series_id}: {e}")
                continue

        # 5) Summary
        logger.info("=" * 50)
        logger.info("📊 FRED Data Load Complete!")
        logger.info(f"✅ Successfully loaded: {successful_loads}/{len(series_ids)} series")
        logger.info(f"📈 Total records inserted: {total_records:,}")
        
        # Check final record count
        cur.execute("SELECT COUNT(*) FROM economic_data")
        final_count = cur.fetchone()[0]
        logger.info(f"🗄️  Total records in database: {final_count:,}")
        
        # Show sample of latest data
        cur.execute("""
            SELECT series_id, date, value 
            FROM economic_data 
            ORDER BY date DESC, series_id 
            LIMIT 10
        """)
        logger.info("📋 Sample of latest data:")
        for row in cur.fetchall():
            logger.info(f"   {row[0]}: {row[2]} ({row[1]})")
        
        logger.info("🎯 Local FRED data loading complete!")
        return 0
        
    except Exception as e:
        logger.error(f"❌ Error loading FRED data: {e}")
        return 1
        
    finally:
        if 'conn' in locals():
            conn.close()
            logger.info("🔌 Database connection closed")

if __name__ == "__main__":
    sys.exit(main())