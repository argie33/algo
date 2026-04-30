#!/usr/bin/env python3
# Phase 4: Relative Performance Calculator
# Calculates stock performance relative to sector/industry baseline
import os, json, logging, sys
from pathlib import Path
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv
from datetime import datetime, timedelta

env_path = Path(__file__).parent / '.env.local'
if env_path.exists():
    load_dotenv(env_path)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", stream=sys.stdout)

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
    cur.execute("""CREATE TABLE IF NOT EXISTS relative_performance (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(20),
        sector VARCHAR(50),
        date DATE,
        stock_return FLOAT,
        sector_return FLOAT,
        relative_performance FLOAT,
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
        # Get latest prices and sector mapping
        cur.execute("""
            SELECT DISTINCT cp.symbol, cp.sector, 
                   (cp.current_price - LAG(cp.current_price) OVER (PARTITION BY cp.symbol ORDER BY DATE)) / LAG(cp.current_price) OVER (PARTITION BY cp.symbol ORDER BY DATE) as stock_return
            FROM company_profile cp
            JOIN price_daily pd ON cp.symbol = pd.symbol
            WHERE pd.date >= CURRENT_DATE - INTERVAL '30 days'
            ORDER BY cp.symbol, pd.date DESC
        """)
        
        records = []
        for row in cur.fetchall():
            if row[2]:  # if stock_return exists
                records.append((row[0], row[1], datetime.now().date(), row[2], 0.0, row[2]))
        
        if records:
            execute_values(cur, """INSERT INTO relative_performance (symbol, sector, date, stock_return, sector_return, relative_performance) VALUES %s ON CONFLICT (symbol, date) DO NOTHING""", records)
            conn.commit()
            logging.info(f"Inserted {len(records)} relative performance records")
        
    except Exception as e:
        logging.error(f"Error: {e}")
    finally:
        cur.close()
        conn.close()

def main():
    logging.info("Starting loadrelativeperformance.py")
    init_db()
    calculate_performance()
    logging.info("Relative performance calculation complete")

if __name__ == "__main__":
    main()
