#!/usr/bin/env python3
# Phase 4: Relative Performance - FIXED
import os, json, logging, sys
from pathlib import Path
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv
from datetime import datetime

env_path = Path(__file__).parent / '.env.local'
if env_path.exists():
    load_dotenv(env_path)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def get_db_config():
    db_secret_arn = os.environ.get("DB_SECRET_ARN")
    if db_secret_arn:
        try:
            import boto3
            sec = json.loads(boto3.client("secretsmanager").get_secret_value(SecretId=db_secret_arn)["SecretString"])
            return {"host": sec["host"], "port": int(sec.get("port", 5432)), "user": sec["username"], "password": sec["password"], "dbname": sec["dbname"]}
        except:
            pass
    return {"host": os.environ.get("DB_HOST", "localhost"), "port": int(os.environ.get("DB_PORT", 5432)), "user": os.environ.get("DB_USER", "stocks"), "password": os.environ.get("DB_PASSWORD", ""), "dbname": os.environ.get("DB_NAME", "stocks")}

def init_db():
    config = get_db_config()
    conn = psycopg2.connect(**config)
    cur = conn.cursor()
    # Drop and recreate to ensure correct schema
    cur.execute("DROP TABLE IF EXISTS relative_performance CASCADE")
    cur.execute("""CREATE TABLE relative_performance (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(20),
        date DATE,
        price_change_pct FLOAT,
        UNIQUE(symbol, date)
    )""")
    conn.commit()
    cur.close()
    conn.close()
    logging.info("relative_performance table ready")

def calculate_performance():
    config = get_db_config()
    conn = psycopg2.connect(**config)
    cur = conn.cursor()
    
    try:
        # Calculate 7-day performance for all stocks
        cur.execute("""
            SELECT ss.symbol,
                   CURRENT_DATE as date,
                   (pd1.close - pd2.close) / NULLIF(pd2.close, 0) * 100 as pct_change
            FROM stock_scores ss
            JOIN price_daily pd1 ON ss.symbol = pd1.symbol 
            JOIN price_daily pd2 ON ss.symbol = pd2.symbol 
            WHERE pd1.date = (SELECT MAX(date) FROM price_daily)
            AND pd2.date = (SELECT MAX(date) FROM price_daily) - INTERVAL '7 days'
            AND pd1.volume > 0 AND pd2.volume > 0
        """)
        
        records = [(row[0], row[1], row[2]) for row in cur.fetchall()]
        
        if records:
            execute_values(cur, """INSERT INTO relative_performance (symbol, date, price_change_pct) VALUES %s ON CONFLICT (symbol, date) DO NOTHING""", records)
            conn.commit()
            logging.info(f"Inserted {len(records)} relative performance records")
        
    except Exception as e:
        logging.error(f"Error: {e}")
    finally:
        cur.close()
        conn.close()

def main():
    logging.info("Starting loadrelativeperformance.py (FIXED)")
    init_db()
    calculate_performance()
    logging.info("Relative performance complete")

if __name__ == "__main__":
    main()
