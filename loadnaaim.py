#!/usr/bin/env python3
import sys
import logging
import json
import os
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
import boto3
import pandas as pd
import requests

# -------------------------------
# Script metadata & logging setup 
# -------------------------------
SCRIPT_NAME = "loadnaaim.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# -------------------------------
# DB config loader
# -------------------------------
def get_db_config():
    secret_str = boto3.client("secretsmanager") \
                     .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
    sec = json.loads(secret_str)
    return {
        "host": sec["host"],
        "port": int(sec.get("port", 5432)),
        "user": sec["username"],
        "password": sec["password"],
        "dbname": sec["dbname"]
    }

def get_naaim_data():
    """Fetch NAAIM exposure index data."""
    url = "https://www.naaim.org/programs/naaim-exposure-index/"
    logging.info(f"Fetching NAAIM data from {url}")
    
    response = requests.get(url)
    response.raise_for_status()
    
    dfs = pd.read_html(response.text)
    if not dfs:
        raise ValueError("No tables found on NAAIM webpage")
    
    df = dfs[0]
    df.columns = [
        'date',
        'mean_exposure',
        'bearish_exposure',
        'quartile1_exposure',
        'quartile2_exposure',
        'quartile3_exposure',
        'bullish_exposure',
        'exposure_deviation'
    ]
    
    # Convert percentage strings to decimals
    percent_columns = [
        'mean_exposure', 'bearish_exposure', 'quartile1_exposure',
        'quartile2_exposure', 'quartile3_exposure', 'bullish_exposure'
    ]
    
    for col in percent_columns:
        df[col] = pd.to_numeric(
            df[col].astype(str).str.replace('%', '').str.strip(),
            errors='coerce'
        ) / 100.0
    
    # Clean up dates
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date'])
    df['date'] = df['date'].dt.strftime('%Y-%m-%d')
    
    df.sort_values('date', inplace=True)
    return df

def main():
    logging.info("Starting NAAIM exposure index data load")
    
    try:
        # Get NAAIM data
        df = get_naaim_data()
        logging.info(f"Retrieved {len(df)} NAAIM exposure records")
        
        # Connect to database
        cfg = get_db_config()
        conn = psycopg2.connect(**cfg)
        conn.autocommit = False
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Recreate table
            logging.info("Recreating naaim_exposure table...")
            cur.execute("DROP TABLE IF EXISTS naaim_exposure CASCADE;")
            cur.execute("""
                CREATE TABLE naaim_exposure (
                    date DATE PRIMARY KEY,
                    mean_exposure DOUBLE PRECISION,
                    bearish_exposure DOUBLE PRECISION,
                    quartile1_exposure DOUBLE PRECISION,
                    quartile2_exposure DOUBLE PRECISION,
                    quartile3_exposure DOUBLE PRECISION,
                    bullish_exposure DOUBLE PRECISION,
                    exposure_deviation DOUBLE PRECISION,
                    fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE INDEX idx_naaim_exposure_date ON naaim_exposure(date);
            """)
            
            # Insert data
            insert_data = [
                (
                    row['date'],
                    row['mean_exposure'],
                    row['bearish_exposure'],
                    row['quartile1_exposure'],
                    row['quartile2_exposure'],
                    row['quartile3_exposure'],
                    row['bullish_exposure'],
                    row['exposure_deviation'],
                    datetime.now()
                )
                for _, row in df.iterrows()
            ]
            
            execute_values(
                cur,
                """
                INSERT INTO naaim_exposure (
                    date, mean_exposure, bearish_exposure,
                    quartile1_exposure, quartile2_exposure, quartile3_exposure,
                    bullish_exposure, exposure_deviation, fetched_at
                ) VALUES %s
                """,
                insert_data,
                page_size=1000
            )
            
            # Update last_updated table
            cur.execute("""
                INSERT INTO last_updated (script_name, last_run)
                VALUES (%s, NOW())
                ON CONFLICT (script_name) DO UPDATE
                    SET last_run = EXCLUDED.last_run;
            """, (SCRIPT_NAME,))
            
            conn.commit()
            logging.info(f"Successfully loaded {len(df)} NAAIM exposure records")
            
        except Exception as e:
            conn.rollback()
            raise e
        
        finally:
            cur.close()
            conn.close()
            
    except Exception as e:
        logging.error(f"Failed to load NAAIM exposure data: {str(e)}")
        sys.exit(1)
    
    logging.info("NAAIM exposure data load completed successfully")

if __name__ == "__main__":
    main()
