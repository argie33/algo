#!/usr/bin/env python3
import os
import sys
import json
import time
import boto3
import logging
import resource
import numpy as np
import pandas as pd
import psycopg2
from datetime import datetime, timedelta
from psycopg2.extras import RealDictCursor, execute_values

# No special numpy patching needed since pandas_ta uses np.nan already

import pandas_ta as ta

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadlatesttechnicalsdaily.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# -------------------------------
# Memory-logging helper (RSS in MB)
# -------------------------------
def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return usage / 1024  # Linux returns KB
    return usage / (1024 * 1024)  # macOS returns B

def log_mem(stage: str):
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")

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

def sanitize_value(x):
    if isinstance(x, float) and np.isnan(x):
        return None
    return x

def calculate_technicals(df):
    """Calculate all technical indicators for a given price dataframe"""
    # Make sure we have enough data for calculations (at least 100 periods)
    if len(df) < 100:
        return None
        
    try:
        # Initialize empty DataFrame for results
        results = pd.DataFrame(index=df.index)
        
        # Moving Averages
        results['sma_20'] = df.ta.sma(length=20)
        results['sma_50'] = df.ta.sma(length=50)
        results['sma_200'] = df.ta.sma(length=200)
        results['ema_12'] = df.ta.ema(length=12)
        results['ema_26'] = df.ta.ema(length=26)
        
        # MACD
        macd = df.ta.macd(fast=12, slow=26, signal=9)
        results['macd'] = macd['MACD_12_26_9']
        results['macd_signal'] = macd['MACDs_12_26_9']
        results['macd_hist'] = macd['MACDh_12_26_9']
        
        # RSI
        results['rsi_14'] = df.ta.rsi(length=14)
        
        # Bollinger Bands
        bbands = df.ta.bbands(length=20)
        results['bb_lower'] = bbands['BBL_20_2.0']
        results['bb_middle'] = bbands['BBM_20_2.0']
        results['bb_upper'] = bbands['BBU_20_2.0']
        
        # ADX
        adx = df.ta.adx(length=14)
        results['adx'] = adx['ADX_14']
        results['di_plus'] = adx['DMP_14']
        results['di_minus'] = adx['DMN_14']
        
        # ATR
        results['atr'] = df.ta.atr(length=14)
        
        # Momentum
        results['roc'] = df.ta.roc(length=9)
        results['mom'] = df.ta.mom(length=10)
        
        # Volume Indicators
        results['obv'] = df.ta.obv()
        results['mfi'] = df.ta.mfi(length=14)
        
        # Clean up any missing values
        results = results.fillna(np.nan)
        return results
        
    except Exception as e:
        logging.error(f"Error calculating technicals: {str(e)}")
        return None

def load_technicals(table_name, symbols, cur, conn):
    """Load technical indicators for given symbols"""
    logging.info(f"Loading {table_name}: {len(symbols)} symbols")
    inserted = 0
    failed = []
    
    for symbol in symbols:
        try:
            # Get the price data for calculations
            cur.execute("""
                SELECT date, open, high, low, close, volume 
                FROM price_daily 
                WHERE symbol = %s 
                ORDER BY date DESC 
                LIMIT 250
            """, (symbol,))
            
            rows = cur.fetchall()
            if not rows:
                logging.warning(f"{table_name} - {symbol}: no price data found")
                failed.append(symbol)
                continue
                
            # Convert to DataFrame
            df = pd.DataFrame(rows)
            df.set_index('date', inplace=True)
            df = df.sort_index()  # Sort by date ascending for calculations
            
            # Calculate technical indicators
            tech_df = calculate_technicals(df)
            if tech_df is None:
                logging.warning(f"{table_name} - {symbol}: failed to calculate technicals")
                failed.append(symbol)
                continue
            
            # Prepare rows for insertion
            insert_rows = []
            for idx, row in tech_df.iterrows():
                values = tuple([symbol, idx] + [sanitize_value(x) for x in row.values])
                insert_rows.append(values)
            
            if not insert_rows:
                logging.warning(f"{table_name} - {symbol}: no valid rows after cleaning")
                failed.append(symbol)
                continue
            
            # Delete existing data for the symbol's dates
            cur.execute(f"""
                DELETE FROM {table_name} 
                WHERE symbol = %s 
                AND date >= %s
            """, (symbol, insert_rows[-1][1]))  # Use earliest date
              # Insert new data with fetched_at timestamp
            columns = ["symbol", "date", "sma_20", "sma_50", "sma_200", "ema_12", "ema_26",
                      "macd", "macd_signal", "macd_hist", "rsi_14", 
                      "bb_lower", "bb_middle", "bb_upper",
                      "adx", "di_plus", "di_minus", "atr",
                      "roc", "mom", "obv", "mfi", "fetched_at"]
            
            # Add current timestamp to each row
            now = datetime.now()
            insert_rows = [row + (now,) for row in insert_rows]
            
            sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES %s"
            execute_values(cur, sql, insert_rows)
            conn.commit()
            
            inserted += len(insert_rows)
            logging.info(f"{table_name} - {symbol}: inserted {len(insert_rows)} rows")
            log_mem(f"{table_name} {symbol} insert end")
            
            time.sleep(0.1)  # Small delay between symbols
            
        except Exception as e:
            logging.error(f"Error processing {symbol}: {str(e)}")
            failed.append(symbol)
            continue
            
    return len(symbols), inserted, failed

# -------------------------------
# Entrypoint
# -------------------------------
if __name__ == "__main__":
    log_mem("startup")

    # Connect to DB
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Get symbols that had price updates in the last run
    cur.execute("""
        WITH last_price_update AS (
            SELECT last_run 
            FROM last_updated 
            WHERE script_name = 'loadlatestpricedaily.py'
        )
        SELECT DISTINCT p.symbol 
        FROM price_daily p
        CROSS JOIN last_price_update l
        WHERE p.updated_at >= l.last_run
    """)
    updated_symbols = [r["symbol"] for r in cur.fetchall()]

    if not updated_symbols:
        logging.info("No symbols with updated prices found")
    else:
        logging.info(f"Found {len(updated_symbols)} symbols with updated prices")
        t_s, i_s, f_s = load_technicals("technical_data_daily", updated_symbols, cur, conn)

        # Record last run
        cur.execute("""
            INSERT INTO last_updated (script_name, last_run)
            VALUES (%s, NOW())
            ON CONFLICT (script_name) DO UPDATE
                SET last_run = EXCLUDED.last_run;
        """, (SCRIPT_NAME,))
        conn.commit()

        peak = get_rss_mb()
        logging.info(f"[MEM] peak RSS: {peak:.1f} MB")
        logging.info(f"Technicals - total: {t_s}, inserted: {i_s}, failed: {len(f_s)}")

    cur.close()
    conn.close()
    logging.info("All done.")