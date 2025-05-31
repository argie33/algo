#!/usr/bin/env python3 
import os # Moved os import earlier
import sys # Moved sys import earlier
import json # Moved json import earlier
import logging # Moved logging import earlier
import gc # For garbage collection
from datetime import datetime
from functools import partial # Not strictly needed in main anymore
import numpy # For monkey-patching
import numpy as np # For monkey-patching and usage
# ───────────────────────────────────────────────────────────────────
# Monkey-patch numpy so that "from numpy import NaN" in pandas_ta will succeed
numpy.NaN = numpy.nan
np.NaN    = np.nan
# ───────────────────────────────────────────────────────────────────
import pandas as pd
import pandas_ta as ta
import boto3
import psycopg2 # Added missing import for psycopg2
from psycopg2 import pool
from psycopg2.extras import execute_values
from concurrent.futures import ProcessPoolExecutor

# Configure these based on your ECS task size
MAX_WORKERS = min(os.cpu_count() or 1, 4)  # Limit to available CPUs or 4, whichever is smaller
BATCH_SIZE = 100  # Number of symbols to process in each batch
DB_POOL_MIN = 2
DB_POOL_MAX = 10

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = os.path.basename(__file__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s",
    stream=sys.stdout
)

def get_db_config():
    """
    Fetch host, port, dbname, username & password from Secrets Manager.
    SecretString must be JSON with keys: username, password, host, port, dbname.
    """
    client = boto3.client("secretsmanager")
    resp = client.get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])
    sec = json.loads(resp["SecretString"])
    return (
        sec["username"],
        sec["password"],
        sec["host"],
        int(sec["port"]),
        sec["dbname"]
    )

def sanitize_value(x):
    if isinstance(x, float) and np.isnan(x):
        return None
    return x

def pivot_high_vectorized(df, left_bars=3, right_bars=3):
    series = df['high']
    roll_left  = series.shift(1).rolling(window=left_bars,  min_periods=left_bars).max()
    roll_right = series.shift(-1).rolling(window=right_bars, min_periods=right_bars).max()
    cond = (series > roll_left) & (series > roll_right)
    return series.where(cond, np.nan)

def pivot_low_vectorized(df, left_bars=3, right_bars=3):
    series = df['low']
    roll_left  = series.shift(1).rolling(window=left_bars,  min_periods=left_bars).min()
    roll_right = series.shift(-1).rolling(window=right_bars, min_periods=right_bars).min()
    cond = (series < roll_left) & (series < roll_right)
    return series.where(cond, np.nan)

def td_sequential(close, lookback=4):
    count = [0]*len(close)
    for i in range(lookback, len(close)):
        if close.iloc[i] < close.iloc[i-lookback]:
            count[i] = count[i-1]+1 if count[i-1]>0 else 1
        elif close.iloc[i] > close.iloc[i-lookback]:
            count[i] = count[i-1]-1 if count[i-1]<0 else -1
        else:
            count[i] = 0
    return pd.Series(count, index=close.index)

def td_combo(close, lookback=2):
    count = [0]*len(close)
    for i in range(lookback, len(close)):
        if close.iloc[i] < close.iloc[i-lookback]:
            count[i] = count[i-1]+1 if count[i-1]>0 else 1
        elif close.iloc[i] > close.iloc[i-lookback]:
            count[i] = count[i-1]-1 if count[i-1]<0 else -1
        else:
            count[i] = 0
    return pd.Series(count, index=close.index)

def marketwatch_indicator(close, open_):
    signal = (close > open_).astype(int) - (close < open_).astype(int)
    count  = [0]*len(signal)
    count[0] = signal.iloc[0]
    for i in range(1, len(signal)):
        if signal.iloc[i]==signal.iloc[i-1] and signal.iloc[i]!=0:
            count[i] = count[i-1] + signal.iloc[i]
        else:
            count[i] = signal.iloc[i]
    return pd.Series(count, index=close.index)

def prepare_db():
    """Set up the database tables"""
    user, pwd, host, port, db = get_db_config()
    conn = psycopg2.connect(
        host=host, port=port, user=user, password=pwd, dbname=db, sslmode='require'
    )
    conn.autocommit = True
    cursor = conn.cursor()
    logging.info("Connected to PostgreSQL database.")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS last_updated (
        script_name VARCHAR(255) PRIMARY KEY,
        last_run    TIMESTAMP
    );
    """)

    # Drop and recreate technical_data_monthly table
    logging.info("Recreating technical_data_monthly table...")
    cursor.execute("DROP TABLE IF EXISTS technical_data_monthly;")
    cursor.execute("""
    CREATE TABLE technical_data_monthly (
        symbol          VARCHAR(50),
        date            TIMESTAMP,
        rsi             DOUBLE PRECISION,
        macd            DOUBLE PRECISION,
        macd_signal     DOUBLE PRECISION,
        macd_hist       DOUBLE PRECISION,
        mom             DOUBLE PRECISION,
        roc             DOUBLE PRECISION,
        adx             DOUBLE PRECISION,
        plus_di         DOUBLE PRECISION,
        minus_di        DOUBLE PRECISION,
        atr             DOUBLE PRECISION,
        ad              DOUBLE PRECISION,
        cmf             DOUBLE PRECISION,
        mfi             DOUBLE PRECISION,
        td_sequential   DOUBLE PRECISION,
        td_combo        DOUBLE PRECISION,
        marketwatch     DOUBLE PRECISION,
        dm              DOUBLE PRECISION,
        sma_10          DOUBLE PRECISION,
        sma_20          DOUBLE PRECISION,
        sma_50          DOUBLE PRECISION,
        sma_150         DOUBLE PRECISION,
        sma_200         DOUBLE PRECISION,
        ema_4           DOUBLE PRECISION,
        ema_9           DOUBLE PRECISION,
        ema_21          DOUBLE PRECISION,
        bbands_lower    DOUBLE PRECISION,
        bbands_middle   DOUBLE PRECISION,
        bbands_upper    DOUBLE PRECISION,
        pivot_high      DOUBLE PRECISION,
        pivot_low       DOUBLE PRECISION,
        fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, date)
    );
    """)
    logging.info("Table 'technical_data_monthly' ready.")
    
    cursor.execute("SELECT symbol FROM stock_symbols;")
    symbols = [r[0] for r in cursor.fetchall()]
    logging.info(f"Found {len(symbols)} symbols.")
    
    cursor.close()
    conn.close()
    
    return symbols

def create_connection_pool():
    """Create a connection pool for better database performance"""
    user, pwd, host, port, db = get_db_config()
    return pool.ThreadedConnectionPool(
        DB_POOL_MIN, DB_POOL_MAX,
        host=host, port=port, user=user, password=pwd, dbname=db, sslmode='require'
    )

def process_symbol(symbol, conn_pool):
    """Process a single symbol and return the number of rows inserted"""
    try:
        conn = conn_pool.getconn()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT date, open, high, low, close, volume
              FROM price_monthly
             WHERE symbol = %s
             ORDER BY date ASC
        """, (symbol,))
        rows = cursor.fetchall()
        
        if not rows:
            logging.warning(f"⚠️ {symbol}: No price data found in price_monthly.") # Adjusted table name
            cursor.close()
            conn_pool.putconn(conn)
            return 0

        # Initialize DataFrame
        df = pd.DataFrame(rows, columns=['date','open','high','low','close','volume'])
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True) # This was missing in the original monthly script

        # Calculate technical indicators (similar to weekly/daily)
        # RSI
        df['rsi'] = ta.rsi(df['close'], length=14)

        # MACD
        macd_df = ta.macd(df['close'], fast=12, slow=26, signal=9)
        if macd_df is not None and not macd_df.empty:
            df['macd'] = macd_df.iloc[:, 0]
            df['macd_hist'] = macd_df.iloc[:, 1]
            df['macd_signal'] = macd_df.iloc[:, 2]
        else:
            df[['macd', 'macd_hist', 'macd_signal']] = np.nan
        
        # Momentum
        df['mom'] = ta.mom(df['close'], length=10)
        
        # ROC
        df['roc'] = ta.roc(df['close'], length=10)

        # ADX + DMI
        adx_df = ta.adx(df['high'], df['low'], df['close'], length=14)
        if adx_df is not None and not adx_df.empty:
            df['adx'] = adx_df.iloc[:, 0]
            df['plus_di'] = adx_df.iloc[:, 1]
            df['minus_di'] = adx_df.iloc[:, 2]
        else:
            df[['adx', 'plus_di', 'minus_di']] = np.nan
            
        df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
        df['ad'] = ta.ad(df['high'], df['low'], df['close'], df['volume'])
        df['cmf'] = ta.cmf(df['high'], df['low'], df['close'], df['volume'], length=20)
        df['mfi'] = ta.mfi(df['high'], df['low'], df['close'], df['volume'], length=14)

        df['td_sequential'] = td_sequential(df['close'], lookback=4)
        df['td_combo'] = td_combo(df['close'], lookback=2)
        df['marketwatch'] = marketwatch_indicator(df['close'], df['open'])

        dm_plus = df['high'].diff()
        dm_minus = df['low'].shift(1) - df['low']
        dm_plus = dm_plus.where((dm_plus>dm_minus)&(dm_plus>0), 0)
        dm_minus = dm_minus.where((dm_minus>dm_plus)&(dm_minus>0), 0)
        df['dm'] = dm_plus - dm_minus

        for p in [10, 20, 50, 150, 200]: # Note: Monthly data might not have enough points for long SMAs
            df[f'sma_{p}'] = ta.sma(df['close'], length=p)
            
        for p in [4, 9, 21]:
            df[f'ema_{p}'] = ta.ema(df['close'], length=p)

        bb = ta.bbands(df['close'], length=20, std=2)
        if bb is not None and not bb.empty:
            df['bbands_lower'] = bb.iloc[:, 0]
            df['bbands_middle'] = bb.iloc[:, 1]
            df['bbands_upper'] = bb.iloc[:, 2]
        else:
            df[['bbands_lower', 'bbands_middle', 'bbands_upper']] = np.nan

        reset_df = df.reset_index()
        df['pivot_high'] = pivot_high_vectorized(reset_df, 3, 3).values
        df['pivot_low'] = pivot_low_vectorized(reset_df, 3, 3).values

        df = df.replace([np.inf, -np.inf], np.nan)

        insert_q = """
        INSERT INTO technical_data_monthly ( # Adjusted table name
          symbol, date,
          rsi, macd, macd_signal, macd_hist,
          mom, roc, adx, plus_di, minus_di, atr, ad, cmf, mfi,
          td_sequential, td_combo, marketwatch, dm,
          sma_10, sma_20, sma_50, sma_150, sma_200,
          ema_4, ema_9, ema_21,
          bbands_lower, bbands_middle, bbands_upper,
          pivot_high, pivot_low,
          fetched_at
        ) VALUES %s;
        """

        data = []
        for idx, row in df.reset_index().iterrows():
            data.append((
                symbol,
                row['date'].to_pydatetime(),
                sanitize_value(row.get('rsi')),
                sanitize_value(row.get('macd')),
                sanitize_value(row.get('macd_signal')),
                sanitize_value(row.get('macd_hist')),
                sanitize_value(row.get('mom')),
                sanitize_value(row.get('roc')),
                sanitize_value(row.get('adx')),
                sanitize_value(row.get('plus_di')),
                sanitize_value(row.get('minus_di')),
                sanitize_value(row.get('atr')),
                sanitize_value(row.get('ad')),
                sanitize_value(row.get('cmf')),
                sanitize_value(row.get('mfi')),
                sanitize_value(row.get('td_sequential')),
                sanitize_value(row.get('td_combo')),
                sanitize_value(row.get('marketwatch')),
                sanitize_value(row.get('dm')),
                sanitize_value(row.get(f'sma_10')),
                sanitize_value(row.get(f'sma_20')),
                sanitize_value(row.get(f'sma_50')),
                sanitize_value(row.get(f'sma_150')),
                sanitize_value(row.get(f'sma_200')),
                sanitize_value(row.get(f'ema_4')),
                sanitize_value(row.get(f'ema_9')),
                sanitize_value(row.get(f'ema_21')),
                sanitize_value(row.get('bbands_lower')),
                sanitize_value(row.get('bbands_middle')),
                sanitize_value(row.get('bbands_upper')),
                sanitize_value(row.get('pivot_high')),
                sanitize_value(row.get('pivot_low')),
                datetime.now()
            ))
        if data:
            execute_values(cursor, insert_q, data)
            conn.commit()
            num_inserted = len(data)
            logging.info(f"✅ {symbol}: Inserted {num_inserted} rows into technical_data_monthly") # Adjusted log
        else:
            num_inserted = 0
            logging.warning(f"⚠️ {symbol}: No data to insert into technical_data_monthly") # Adjusted log
        
        cursor.close()
        conn_pool.putconn(conn)
        
        del df, data, rows, reset_df
        if 'macd_df' in locals(): del macd_df
        if 'adx_df' in locals(): del adx_df
        if 'bb' in locals(): del bb
        gc.collect()
        
        return num_inserted
        
    except Exception as e:
        logging.error(f"❌ {symbol}: Failed in process_symbol (monthly) - {str(e)}") # Adjusted log
        if 'conn' in locals() and conn:
            conn_pool.putconn(conn)
        if 'df' in locals(): del df
        if 'data' in locals(): del data
        if 'rows' in locals(): del rows
        if 'reset_df' in locals(): del reset_df
        if 'macd_df' in locals(): del macd_df
        if 'adx_df' in locals(): del adx_df
        if 'bb' in locals(): del bb
        gc.collect()
        return 0

def process_symbol_batch(symbols_batch, conn_pool_outer=None): # Added default for conn_pool_outer for flexibility
    """Process a batch of symbols and return total inserted, success and failure counts."""
    conn_pool = create_connection_pool() # Each batch process creates its own pool
    
    total_inserted = 0
    success_count = 0
    failed_count = 0
    
    try:
        for symbol in symbols_batch:
            try:
                inserted = process_symbol(symbol, conn_pool)
                total_inserted += inserted
                if inserted > 0:
                    success_count += 1
                else:
                    failed_count += 1 
            except Exception as e:
                logging.error(f"❌ Batch error for {symbol} (monthly): {str(e)}") # Adjusted log
                failed_count += 1
    finally:
        if conn_pool:
            conn_pool.closeall()
            
    return total_inserted, success_count, failed_count

def main():
    logging.info(f"Starting {SCRIPT_NAME}")
    start_time = datetime.now()
    try:
        symbols = prepare_db()
        if not symbols:
            logging.info("No symbols to process.")
            return

        total_rows_inserted = 0
        total_success_symbols = 0
        total_failed_symbols = 0

        symbol_batches = [symbols[i:i + BATCH_SIZE] for i in range(0, len(symbols), BATCH_SIZE)]
        
        with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # process_symbol_batch will create its own connection pool internally
            results = list(executor.map(process_symbol_batch, symbol_batches))

        for inserted, success, failed in results:
            total_rows_inserted += inserted
            total_success_symbols += success
            total_failed_symbols += failed

        logging.info(f"All batches processed for {SCRIPT_NAME}.")
        logging.info(f"Total symbols processed: {len(symbols)}")
        logging.info(f"Successfully processed symbols: {total_success_symbols}")
        logging.info(f"Failed symbols: {total_failed_symbols}")
        logging.info(f"Total rows inserted: {total_rows_inserted}")

        user, pwd, host, port, db_name = get_db_config()
        conn = psycopg2.connect(host=host, port=port, user=user, password=pwd, dbname=db_name, sslmode='require')
        conn.autocommit = True
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO last_updated (script_name, last_run)
            VALUES (%s, %s)
            ON CONFLICT (script_name) DO UPDATE SET last_run = %s;
        """, (SCRIPT_NAME, start_time, start_time))
        cursor.close()
        conn.close()
        logging.info(f"Updated last_run time for {SCRIPT_NAME} to {start_time}")

    except Exception as e:
        logging.critical(f"💥 CRITICAL ERROR in main (monthly): {str(e)}", exc_info=True) # Adjusted log
    finally:
        end_time = datetime.now()
        logging.info(f"Finished {SCRIPT_NAME}. Total execution time: {end_time - start_time}")

if __name__ == "__main__":
    main()
