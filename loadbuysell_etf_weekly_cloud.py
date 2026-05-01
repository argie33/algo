#!/usr/bin/env python3
"""
Cloud-Native ETF Buy/Sell Weekly Signals Loader
Uses S3 staging + PostgreSQL COPY FROM S3 for 1000x faster bulk loading
"""

import sys
import time
import logging
import os
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional

import psycopg2
import boto3
import pandas as pd
import yfinance as yf

from s3_bulk_insert import S3BulkInsert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

def get_db_config():
    """Get RDS config from Secrets Manager (AWS best practice)"""
    aws_region = os.environ.get("AWS_REGION", "us-east-1")
    db_secret_arn = os.environ.get("DB_SECRET_ARN")

    if db_secret_arn:
        try:
            secret = boto3.client("secretsmanager", region_name=aws_region).get_secret_value(
                SecretId=db_secret_arn
            )
            creds = json.loads(secret["SecretString"])
            return {
                "host": creds["host"],
                "port": int(creds.get("port", 5432)),
                "user": creds["username"],
                "password": creds["password"],
                "dbname": creds["dbname"],
                "connect_timeout": 10
            }
        except Exception as e:
            logging.warning(f"Secrets Manager failed: {e}, falling back to env vars")

    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", 5432)),
        "user": os.environ.get("DB_USER", "stocks"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "dbname": os.environ.get("DB_NAME", "stocks"),
        "connect_timeout": 10
    }

def get_rds_s3_role():
    return os.environ.get(
        "RDS_S3_ROLE_ARN",
        "arn:aws:iam::626216981288:role/RDSBulkInsertRole"
    )

def load_etf_signals(symbol: str) -> List[tuple]:
    """Load weekly buy/sell signals for ETF"""
    try:
        ticker = yf.Ticker(symbol.replace(".", "-").upper())
        hist = ticker.history(period="max", interval="1wk")

        if hist.empty:
            return []

        # Simplified signal generation for cloud version
        # Uses volume surge + price momentum
        hist['volume_avg'] = hist['Volume'].rolling(4).mean()
        hist['volume_surge'] = (hist['Volume'] / hist['volume_avg']).fillna(1)
        hist['price_change'] = hist['Close'].pct_change()
        hist['ma_20'] = hist['Close'].rolling(20).mean()

        rows = []
        for date, row in hist.iterrows():
            # Basic buy/sell signal logic
            signal = None
            if row['volume_surge'] > 1.5 and row['price_change'] > 0.02:
                signal = 'Buy'
            elif row['volume_surge'] > 1.5 and row['price_change'] < -0.02:
                signal = 'Sell'

            if signal:
                rows.append((
                    symbol,
                    'weekly',
                    date.date(),
                    float(row["Open"]) if pd.notna(row["Open"]) else None,
                    float(row["High"]) if pd.notna(row["High"]) else None,
                    float(row["Low"]) if pd.notna(row["Low"]) else None,
                    float(row["Close"]) if pd.notna(row["Close"]) else None,
                    int(row["Volume"]) if pd.notna(row["Volume"]) else None,
                    signal,
                    None,  # signal_triggered_date
                    None,  # buylevel
                    None,  # stoplevel
                    False, # inposition
                    100,   # strength
                    'weekly',  # signal_type
                    None,  # pivot_price
                    None, None, None, None, None, None, None, None,  # exit triggers and stops
                    None, None, None, None, None, None,  # base info
                    None, None, None,  # risk metrics
                    None, None, None,  # profit targets
                    None, None, None, None, None, None,  # stage/substage
                    None, None, None, None,  # market stage
                    None, None, None, None, None, None, None, None, None  # technical indicators
                ))

        logging.debug(f"[OK] {symbol}: {len(rows)} weekly signal rows")
        return rows

    except Exception as e:
        logging.error(f"Error loading ETF {symbol}: {e}")
        return []

def main():
    logging.info("Starting loadbuysell_etf_weekly_cloud (PARALLEL + S3 BULK)")

    db_config = get_db_config()
    rds_role = get_rds_s3_role()
    s3_bucket = os.environ.get("S3_STAGING_BUCKET", "stocks-app-data")

    # Get ETF symbols
    try:
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT symbol FROM stock_symbols LIMIT 500")
        symbols = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"Failed to fetch symbols: {e}")
        return False

    total_symbols = len(symbols)
    logging.info(f"Loading weekly ETF signals for {total_symbols} ETFs...")

    all_rows = []
    successful = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_symbol = {
            executor.submit(load_etf_signals, symbol): symbol
            for symbol in symbols
        }

        completed = 0
        start_time = time.time()

        for future in as_completed(future_to_symbol):
            symbol = future_to_symbol[future]
            completed += 1

            try:
                rows = future.result()
                if rows:
                    all_rows.extend(rows)
                    successful += 1
                else:
                    failed += 1

                if completed % 50 == 0:
                    elapsed = time.time() - start_time
                    rate = completed / elapsed if elapsed > 0 else 0
                    remaining = (total_symbols - completed) / rate if rate > 0 else 0
                    logging.info(
                        f"Progress: {completed}/{total_symbols} "
                        f"({rate:.1f}/sec, ~{remaining:.0f}s remaining, {len(all_rows)} rows)"
                    )

            except Exception as e:
                failed += 1
                logging.error(f"Error with {symbol}: {e}")

    # Bulk insert all rows via S3
    if all_rows:
        try:
            logging.info(f"Bulk inserting {len(all_rows)} rows via S3...")
            bulk_inserter = S3BulkInsert(s3_bucket, db_config)
            columns = [
                'symbol', 'timeframe', 'date', 'open', 'high', 'low', 'close', 'volume',
                'signal', 'signal_triggered_date', 'buylevel', 'stoplevel', 'inposition', 'strength',
                'signal_type', 'pivot_price', 'buy_zone_start', 'buy_zone_end',
                'exit_trigger_1_price', 'exit_trigger_2_price', 'exit_trigger_3_condition', 'exit_trigger_3_price',
                'exit_trigger_4_condition', 'exit_trigger_4_price', 'initial_stop', 'trailing_stop',
                'base_type', 'base_length_days', 'avg_volume_50d', 'volume_surge_pct',
                'rs_rating', 'breakout_quality', 'risk_reward_ratio',
                'profit_target_8pct', 'profit_target_20pct', 'profit_target_25pct',
                'risk_pct', 'entry_quality_score', 'market_stage', 'stage_number', 'stage_confidence', 'substage',
                'position_size_recommendation', 'current_gain_pct', 'days_in_position', 'sell_level',
                'mansfield_rs', 'sata_score',
                'rsi', 'adx', 'atr', 'sma_50', 'sma_200', 'ema_21', 'pct_from_ema21', 'pct_from_sma50', 'entry_price'
            ]
            inserted = bulk_inserter.insert_bulk("buy_sell_etf_weekly", columns, all_rows, rds_role)

            elapsed = time.time() - start_time
            logging.info(
                f"[OK] Completed: {inserted} rows inserted, "
                f"{successful} successful, {failed} failed "
                f"in {elapsed:.1f}s ({elapsed/60:.1f}m)"
            )
            return True

        except Exception as e:
            logging.error(f"Bulk insert failed: {e}")
            return False
    else:
        logging.warning("No data to insert")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
