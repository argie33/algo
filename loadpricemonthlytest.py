import time
import logging
from datetime import datetime
import pymysql
import pandas as pd
import yfinance as yf

# --- Setup Logging ---
logging.basicConfig(
    filename="loadpricemonthly.log",
    level=logging.ERROR,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# --- Database Connection Setup ---
db_config = {
    'host': 'localhost',
    'user': 'stocks',
    'password': 'bed0elAn',
    'database': 'stocks',
    'cursorclass': pymysql.cursors.DictCursor,
    'autocommit': True
}
conn = pymysql.connect(**db_config)
cursor = conn.cursor()
print("Connected to the database.")

# --- Drop and Create the price_data_montly Table ---
print("Dropping and creating the table 'price_data_montly'...")
cursor.execute("DROP TABLE IF EXISTS price_data_montly")
conn.commit()

create_table_query = """
CREATE TABLE price_data_montly (
    symbol VARCHAR(20),
    date DATE,
    open DECIMAL(20,4),
    high DECIMAL(20,4),
    low DECIMAL(20,4),
    close DECIMAL(20,4),
    volume BIGINT,
    dividends DECIMAL(20,4),
    stock_splits DECIMAL(20,4)
)
"""
cursor.execute(create_table_query)
conn.commit()
print("Table 'price_data_montly' created.")

# --- Retrieve Symbols from stock_symbols Table ---
print("Fetching symbols from the 'stock_symbols' table...")
cursor.execute("SELECT symbol FROM stock_symbols")
symbols = [row['symbol'] for row in cursor.fetchall()]
print(f"Found {len(symbols)} symbols.")

# --- Parameters for Rate Limiting and Retry ---
MAX_RETRIES = 3
RETRY_DELAY = 5      # seconds between retries
RATE_LIMIT_DELAY = 1  # seconds between symbols

def fetch_monthly_data(symbol, retries=MAX_RETRIES):
    """
    Fetch monthly historical data for a symbol using yfinance.
    Returns a DataFrame or None if it fails.
    """
    yf_symbol = symbol.replace('.', '-')
    for attempt in range(1, retries+1):
        try:
            df = yf.download(
                yf_symbol,
                period="max",
                interval="1mo",
                progress=False,
                auto_adjust=False,
                threads=False
            )
            if df is None or df.empty:
                raise ValueError("No data returned")
            return df
        except Exception as e:
            logging.error(f"Error fetching {symbol} (attempt {attempt}): {e}")
            print(f"Error fetching data for {symbol} (attempt {attempt}). Retrying in {RETRY_DELAY}s...")
            if attempt < retries:
                time.sleep(RETRY_DELAY)
            else:
                logging.error(f"Failed to fetch monthly data for {symbol} after {retries} attempts.")
                return None

print("Starting to process each symbol...")
for idx, symbol in enumerate(symbols, start=1):
    print(f"[{idx}/{len(symbols)}] Processing {symbol}...")
    df = fetch_monthly_data(symbol)
    if df is not None:
        print(f"  Fetched {len(df)} rows for {symbol}.")
        df = df.reset_index()
        df['symbol'] = symbol

        # Ensure required columns exist
        for col in ['Open','High','Low','Close','Volume','Dividends','Stock Splits']:
            if col not in df.columns:
                df[col] = 0.0

        # Rename to match schema
        df.rename(columns={
            'Date': 'date',
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume',
            'Dividends': 'dividends',
            'Stock Splits': 'stock_splits'
        }, inplace=True)

        # Prepare batch insert
        to_insert = df[['symbol','date','open','high','low','close','volume','dividends','stock_splits']]
        data_tuples = list(to_insert.itertuples(index=False, name=None))

        insert_sql = """
            INSERT INTO price_data_montly
            (symbol, date, open, high, low, close, volume, dividends, stock_splits)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        try:
            cursor.executemany(insert_sql, data_tuples)
            conn.commit()
            print(f"  Inserted {len(data_tuples)} rows for {symbol}.")
        except Exception as e:
            logging.error(f"DB insert error for {symbol}: {e}")
            print(f"  Error inserting data for {symbol}. See log for details.")
    else:
        print(f"  No data for {symbol}. Skipping.")

    time.sleep(RATE_LIMIT_DELAY)

# --- Update last_updated Table ---
script_name = "loadpricemonthly.py"
current_time = datetime.now()

update_sql = """
INSERT INTO last_updated (script_name, last_updated)
VALUES (%s, %s)
ON DUPLICATE KEY UPDATE last_updated = VALUES(last_updated)
"""
try:
    cursor.execute(update_sql, (script_name, current_time))
    conn.commit()
    print(f"Updated last_updated for '{script_name}' at {current_time}.")
except Exception as e:
    logging.error(f"Error updating last_updated: {e}")
    print("Error updating last_updated table. See log for details.")

cursor.close()
conn.close()
print("Monthly data fetching and insertion complete.")
