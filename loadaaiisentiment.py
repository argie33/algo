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
from io import BytesIO

# -------------------------------
# Script metadata & logging setup 
# -------------------------------
SCRIPT_NAME = "loadaaiisentiment.py"
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

def get_aaii_sentiment_data():
    """Downloads and processes AAII sentiment survey data."""
    AAII_EXCEL_URL = "https://www.aaii.com/files/surveys/sentiment.xls"
    
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/115.0.0.0 Safari/537.36"),
        "Referer": "https://www.aaii.com/",
        "Accept": "application/vnd.ms-excel",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    logging.info(f"Downloading AAII sentiment data from {AAII_EXCEL_URL}")
    response = requests.get(AAII_EXCEL_URL, headers=headers, allow_redirects=True)
    response.raise_for_status()
    
    content_type = response.headers.get("Content-Type", "")
    if "html" in content_type.lower():
        raise ValueError("Server returned HTML instead of Excel file")
    
    excel_data = BytesIO(response.content)
    df = pd.read_excel(excel_data, skiprows=3, engine="xlrd")
    df.columns = df.columns.str.strip()
    
    required_cols = ["Date", "Bullish", "Neutral", "Bearish"]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing columns: {missing_cols}")
    
    df = df[required_cols]
    
    # Clean percentage columns
    for col in ["Bullish", "Neutral", "Bearish"]:
        df[col] = df[col].astype(str).str.replace("%", "").str.strip()
        df[col] = pd.to_numeric(df[col], errors="coerce") / 100.0  # Convert to decimals
    
    # Clean dates
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
    
    df.sort_values("Date", inplace=True)
    return df

def main():
    logging.info("Starting AAII sentiment data load")
    
    try:
        # Get sentiment data
        df = get_aaii_sentiment_data()
        logging.info(f"Retrieved {len(df)} AAII sentiment records")
        
        # Connect to database
        cfg = get_db_config()
        conn = psycopg2.connect(**cfg)
        conn.autocommit = False
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Recreate table
            logging.info("Recreating aaii_sentiment table...")
            cur.execute("DROP TABLE IF EXISTS aaii_sentiment CASCADE;")
            cur.execute("""
                CREATE TABLE aaii_sentiment (
                    date DATE PRIMARY KEY,
                    bullish DOUBLE PRECISION,
                    neutral DOUBLE PRECISION,
                    bearish DOUBLE PRECISION,
                    fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE INDEX idx_aaii_sentiment_date ON aaii_sentiment(date);
            """)
            
            # Insert data
            insert_data = [
                (
                    row["Date"],
                    row["Bullish"],
                    row["Neutral"],
                    row["Bearish"],
                    datetime.now()
                )
                for _, row in df.iterrows()
            ]
            
            execute_values(
                cur,
                """
                INSERT INTO aaii_sentiment (
                    date, bullish, neutral, bearish, fetched_at
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
            logging.info(f"Successfully loaded {len(df)} AAII sentiment records")
            
        except Exception as e:
            conn.rollback()
            raise e
        
        finally:
            cur.close()
            conn.close()
            
    except Exception as e:
        logging.error(f"Failed to load AAII sentiment data: {str(e)}")
        sys.exit(1)
    
    logging.info("AAII sentiment data load completed successfully")

if __name__ == "__main__":
    main()
