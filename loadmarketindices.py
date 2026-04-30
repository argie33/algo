#!/usr/bin/env python3
# Phase 4 Cloud Completion: Market Indices Loader
# Loads market index data (S&P 500, Dow Jones, Nasdaq, Russell, etc.)
import sys, logging, json, os
from pathlib import Path
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import execute_values
import yfinance as yf
from dotenv import load_dotenv

env_path = Path(__file__).parent / '.env.local'
if env_path.exists():
    load_dotenv(env_path)

SCRIPT_NAME = "loadmarketindices.py"
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", stream=sys.stdout)

MARKET_INDICES = {
    '^GSPC': 'S&P 500', '^IXIC': 'Nasdaq', '^DJI': 'Dow Jones',
    '^RUT': 'Russell 2000', '^FTSE': 'FTSE 100', '^N225': 'Nikkei 225',
    '^VIX': 'VIX', '^GDAXI': 'DAX', '^FCHI': 'CAC 40',
}

def get_db_config():
    db_secret_arn = os.environ.get("DB_SECRET_ARN")
    if db_secret_arn:
        try:
            import boto3
            secret = boto3.client("secretsmanager").get_secret_value(SecretId=db_secret_arn)["SecretString"]
            sec = json.loads(secret)
            return {"host": sec["host"], "port": int(sec.get("port", 5432)), "user": sec["username"], "password": sec["password"], "dbname": sec["dbname"]}
        except:
            pass
    return {"host": os.environ.get("DB_HOST", "localhost"), "port": int(os.environ.get("DB_PORT", 5432)), "user": os.environ.get("DB_USER", "stocks"), "password": os.environ.get("DB_PASSWORD", ""), "dbname": os.environ.get("DB_NAME", "stocks")}

def init_db():
    config = get_db_config()
    conn = psycopg2.connect(**config)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS market_indices (id SERIAL PRIMARY KEY, symbol VARCHAR(20), name VARCHAR(100), date DATE, open FLOAT, high FLOAT, low FLOAT, close FLOAT, volume BIGINT, UNIQUE(symbol, date))""")
    conn.commit()
    cur.close()
    conn.close()

def load_indices():
    all_records = []
    for symbol, name in MARKET_INDICES.items():
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=365)
            df = yf.Ticker(symbol).history(start=start_date, end=end_date)
            
            for idx, row in df.iterrows():
                if row['Volume'] > 0:
                    all_records.append((symbol, name, idx.date(), float(row['Open']), float(row['High']), float(row['Low']), float(row['Close']), int(row['Volume'])))
            logging.info(f"{symbol}: {len([r for r in all_records if r[0] == symbol])} records")
        except Exception as e:
            logging.error(f"{symbol}: {e}")
    return all_records

def insert_data(records):
    config = get_db_config()
    conn = psycopg2.connect(**config)
    cur = conn.cursor()
    execute_values(cur, "INSERT INTO market_indices (symbol, name, date, open, high, low, close, volume) VALUES %s ON CONFLICT (symbol, date) DO NOTHING", records, page_size=1000)
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM market_indices")
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count

def main():
    logging.info(f"Starting {SCRIPT_NAME}")
    init_db()
    records = load_indices()
    logging.info(f"Inserting {len(records)} records...")
    count = insert_data(records)
    logging.info(f"Market indices loaded: {count:,} total records")

if __name__ == "__main__":
    main()
