#!/usr/bin/env python3 
import sys
import time
import logging
import json
import os
import gc
import psutil
import warnings
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from functools import partial

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
import boto3
import numpy as np
import pandas as pd

# Suppress warnings for performance
warnings.simplefilter(action='ignore', category=FutureWarning)
warnings.simplefilter(action='ignore', category=pd.errors.PerformanceWarning)

# -------------------------------
# Script metadata & logging setup 
# -------------------------------
SCRIPT_NAME = "loadtechnicalsdaily.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

logging.info("✅ Using Pure NumPy/Pandas Implementation - No TA-Lib Dependencies!")

# -------------------------------
# Memory-logging helper (RSS in MB) - Cross-platform compatible
# -------------------------------
def get_rss_mb():
    """Get RSS memory usage in MB - works on all platforms"""
    return psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024

def log_mem(stage: str):
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")

# -------------------------------
# Pure NumPy/Pandas Technical Indicators (No TA-Lib dependencies)
# Same as weekly/monthly - COMPLETE IMPLEMENTATION
# -------------------------------

def sma_fast(values, period):
    """Ultra-fast SMA using numpy convolution"""
    if len(values) < period:
        return pd.Series(np.full(len(values), np.nan), index=values.index)
    
    kernel = np.ones(period) / period
    result = np.convolve(values.values, kernel, mode='valid')
    padded_result = np.concatenate([np.full(period - 1, np.nan), result])
    return pd.Series(padded_result, index=values.index)

def ema_fast(values, period):
    """Ultra-fast EMA implementation"""
    if len(values) < 1:
        return pd.Series(np.full(len(values), np.nan), index=values.index)
    
    alpha = 2.0 / (period + 1.0)
    result = np.empty_like(values.values, dtype=np.float64)
    
    first_valid_idx = values.first_valid_index()
    if first_valid_idx is None:
        return pd.Series(np.full(len(values), np.nan), index=values.index)
    
    first_valid_pos = values.index.get_loc(first_valid_idx)
    result[:first_valid_pos] = np.nan
    result[first_valid_pos] = values.iloc[first_valid_pos]
    
    for i in range(first_valid_pos + 1, len(values)):
        if np.isnan(values.iloc[i]):
            result[i] = result[i-1]
        else:
            result[i] = alpha * values.iloc[i] + (1 - alpha) * result[i - 1]
    
    return pd.Series(result, index=values.index)

def rsi_fast(values, period=14):
    """Lightning-fast RSI"""
    if len(values) < period + 1:
        return pd.Series(np.full(len(values), np.nan), index=values.index)
    
    changes = values.diff()
    gains = changes.where(changes > 0, 0)
    losses = -changes.where(changes < 0, 0)
    
    avg_gains = gains.ewm(span=period, adjust=False).mean()
    avg_losses = losses.ewm(span=period, adjust=False).mean()
    
    rs = avg_gains / (avg_losses + 1e-10)
    rsi = 100 - (100 / (1 + rs))
    
    return rsi.fillna(50)

def macd_fast(values, fast=12, slow=26, signal=9):
    """Ultra-fast MACD"""
    if len(values) < slow:
        nan_series = pd.Series(np.full(len(values), np.nan), index=values.index)
        return nan_series, nan_series, nan_series
    
    ema_fast_line = ema_fast(values, fast)
    ema_slow_line = ema_fast(values, slow)
    
    macd_line = ema_fast_line - ema_slow_line
    signal_line = ema_fast(macd_line, signal)
    histogram = macd_line - signal_line
    
    return macd_line, signal_line, histogram

def bollinger_bands_fast(values, period=20, std_multiplier=2):
    """Ultra-fast Bollinger Bands"""
    if len(values) < period:
        nan_series = pd.Series(np.full(len(values), np.nan), index=values.index)
        return nan_series, nan_series, nan_series
    
    middle = sma_fast(values, period)
    rolling_std = values.rolling(window=period, min_periods=period).std()
    
    upper = middle + (std_multiplier * rolling_std)
    lower = middle - (std_multiplier * rolling_std)
    
    return lower, middle, upper

def atr_fast(high, low, close, period=14):
    """Average True Range"""
    if len(high) < 2:
        return pd.Series(np.full(len(high), np.nan), index=high.index)
    
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.ewm(span=period, adjust=False).mean()
    return atr.fillna(0)

def adx_fast(high, low, close, period=14):
    """ADX implementation - simplified but accurate"""
    if len(high) < period + 1:
        return pd.Series(np.full(len(high), np.nan), index=high.index)
    
    # Calculate directional movement
    high_diff = high.diff()
    low_diff = low.shift(1) - low
    
    plus_dm = pd.Series(np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0), index=high.index)
    minus_dm = pd.Series(np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0), index=high.index)
    
    # True Range
    tr = atr_fast(high, low, close, 1)
    
    # Smooth DM and TR
    plus_dm_smooth = plus_dm.ewm(span=period, adjust=False).mean()
    minus_dm_smooth = minus_dm.ewm(span=period, adjust=False).mean()
    tr_smooth = tr.ewm(span=period, adjust=False).mean()
    
    # Calculate DI
    plus_di = 100 * plus_dm_smooth / (tr_smooth + 1e-10)
    minus_di = 100 * minus_dm_smooth / (tr_smooth + 1e-10)
    
    # Calculate DX
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10)
    
    # ADX is EMA of DX
    adx = dx.ewm(span=period, adjust=False).mean()
    
    return adx.fillna(0)

def momentum_fast(values, period=10):
    """Momentum indicator"""
    if len(values) < period:
        return pd.Series(np.full(len(values), np.nan), index=values.index)
    
    momentum = values - values.shift(period)
    return momentum.fillna(0)

def roc_fast(values, period=10):
    """Rate of Change"""
    if len(values) < period:
        return pd.Series(np.full(len(values), np.nan), index=values.index)
    
    shifted = values.shift(period)
    roc = ((values - shifted) / (shifted + 1e-10)) * 100
    return roc.fillna(0)

def td_sequential_vectorized(close, lookback=4):
    """Vectorized TD Sequential indicator"""
    if len(close) < lookback + 1:
        return pd.Series(np.zeros(len(close)), index=close.index)
    
    # Compare current close with close N periods ago
    comparison = np.where(close < close.shift(lookback), 1, 
                         np.where(close > close.shift(lookback), -1, 0))
    
    result = np.zeros(len(close))
    count = 0
    current_direction = 0
    
    for i in range(lookback, len(close)):
        if comparison[i] == 1:  # Bearish
            if current_direction == 1:
                count += 1
            else:
                count = 1
                current_direction = 1
            result[i] = count
        elif comparison[i] == -1:  # Bullish
            if current_direction == -1:
                count -= 1
            else:
                count = -1
                current_direction = -1
            result[i] = count
        else:  # No signal
            count = 0
            current_direction = 0
    
    return pd.Series(result, index=close.index)

def td_combo_vectorized(close, lookback=2):
    """Vectorized TD Combo indicator"""
    if len(close) < lookback + 1:
        return pd.Series(np.zeros(len(close)), index=close.index)
    
    # Similar to TD Sequential but with different lookback
    comparison = np.where(close < close.shift(lookback), 1, 
                         np.where(close > close.shift(lookback), -1, 0))
    
    result = np.zeros(len(close))
    count = 0
    current_direction = 0
    
    for i in range(lookback, len(close)):
        if comparison[i] == 1:  # Bearish
            if current_direction == 1:
                count += 1
            else:
                count = 1
                current_direction = 1
            result[i] = count
        elif comparison[i] == -1:  # Bullish
            if current_direction == -1:
                count -= 1
            else:
                count = -1
                current_direction = -1
            result[i] = count
        else:  # No signal
            count = 0
            current_direction = 0
    
    return pd.Series(result, index=close.index)

def calculate_technicals_parallel(df):
    """Calculate all technical indicators using parallel processing where beneficial - COMPLETE IMPLEMENTATION"""
    logging.info(f"🔧 Starting technical calculations for {len(df)} rows of data")
    
    # Ensure proper data types
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Fill gaps and drop NaN rows
    original_len = len(df)
    df = df.ffill().bfill().dropna()
    
    if len(df) != original_len:
        logging.info(f"📊 Cleaned data: {original_len} → {len(df)} rows after removing NaN")
    
    if len(df) < 50:  # Need minimum data for calculations
        logging.warning(f"⚠️ Insufficient data for technicals: {len(df)} rows (need at least 50)")
        return None
    
    try:
        results = {}
        
        # Basic indicators
        logging.info("🔄 Calculating basic indicators...")
        results['rsi'] = rsi_fast(df['close'], period=14)
        results['mom'] = momentum_fast(df['close'], period=10)
        results['roc'] = roc_fast(df['close'], period=10)
        
        # Moving averages
        logging.info("🔄 Calculating moving averages...")
        for period in [10, 20, 50, 150, 200]:
            results[f'sma_{period}'] = sma_fast(df['close'], period)
        
        for period in [4, 9, 21]:
            results[f'ema_{period}'] = ema_fast(df['close'], period)
        
        # Complex indicators
        logging.info("🔄 Calculating complex indicators...")
        
        # MACD
        macd_line, signal_line, histogram = macd_fast(df['close'], fast=12, slow=26, signal=9)
        results['macd'] = macd_line
        results['macd_signal'] = signal_line
        results['macd_hist'] = histogram
        
        # ADX (computationally expensive)
        results['adx'] = adx_fast(df['high'], df['low'], df['close'], period=14)
        
        # Bollinger Bands
        bb_lower, bb_middle, bb_upper = bollinger_bands_fast(df['close'], period=20, std_dev=2)
        results['bbands_lower'] = bb_lower
        results['bbands_middle'] = bb_middle
        results['bbands_upper'] = bb_upper
        
        # ATR
        results['atr'] = atr_fast(df['high'], df['low'], df['close'], period=14)
        
        # Custom indicators
        logging.info("🔄 Calculating custom indicators...")
        results['td_sequential'] = td_sequential_vectorized(df['close'], lookback=4)
        results['td_combo'] = td_combo_vectorized(df['close'], lookback=2)
        
        # Combine all results into the original dataframe
        for key, series in results.items():
            df[key] = series
        
        logging.info(f"✅ Technical calculations completed successfully for {len(results)} indicators")
        return df
        
    except Exception as e:
        logging.error(f"❌ Failed to calculate technicals: {e}")
        import traceback
        logging.error(f"❌ Full traceback: {''.join(traceback.format_exc())}")
        return None

def validate_prerequisites(cur):
    """Validate that prerequisites for loading technical data are met"""
    try:
        logging.info("🔍 Step 1: Checking if price_daily table exists...")
        
        # Check if price_daily table exists and has data
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'price_daily'
            ) as table_exists
        """)
        result = cur.fetchone()
        price_table_exists = result['table_exists']
        logging.info(f"📊 price_daily table exists: {price_table_exists}")
        
        if not price_table_exists:
            logging.error("❌ price_daily table does not exist. Technical data requires price data.")
            logging.error("💡 Hint: Run the price data loader first (pricedaily-loader) to populate price_daily table")
            return False
        
        logging.info("🔍 Step 2: Checking if price_daily table has data...")
        
        # Check total number of rows first
        cur.execute("SELECT COUNT(*) as total_rows FROM price_daily")
        result = cur.fetchone()
        total_rows = result['total_rows']
        logging.info(f"📊 Total rows in price_daily: {total_rows}")
        
        if total_rows == 0:
            logging.error("❌ price_daily table exists but is empty (0 rows)")
            logging.error("💡 Hint: Run the price data loader first (pricedaily-loader) to populate price_daily table")
            return False
        
        # Check if we have price data for symbols
        logging.info("🔍 Step 3: Counting distinct symbols in price_daily...")
        cur.execute("SELECT COUNT(DISTINCT symbol) as symbol_count FROM price_daily")
        result = cur.fetchone()
        price_symbol_count = result['symbol_count'] if result else 0
        logging.info(f"📊 Distinct symbols in price_daily: {price_symbol_count}")
        
        if price_symbol_count == 0:
            logging.error("❌ No distinct symbols found in price_daily table")
            logging.error("💡 This is unusual - table has rows but no distinct symbols")
            return False
        
        logging.info(f"✅ Prerequisites met: price_daily table exists with {price_symbol_count} symbols")
        return True
        
    except Exception as e:
        logging.error(f"❌ Exception type: {type(e).__name__}")
        logging.error(f"❌ Exception details: {repr(e)}")
        logging.error(f"❌ Full traceback: {str(e)}")
        import traceback
        logging.error(f"❌ Full traceback: {''.join(traceback.format_exc())}")
        return False

def delete_existing_table(cur):
    """Delete existing technical_data_daily table and confirm deletion"""
    try:
        logging.info("🗑️ Step 1: Checking if technical_data_daily table exists...")
        
        # Check if table exists
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'technical_data_daily'
            ) as table_exists
        """)
        result = cur.fetchone()
        table_exists = result['table_exists']
        
        if table_exists:
            logging.info("📊 technical_data_daily table exists, checking row count...")
            
            # Count existing rows
            cur.execute("SELECT COUNT(*) as row_count FROM technical_data_daily")
            result = cur.fetchone()
            existing_rows = result['row_count']
            logging.info(f"📊 Existing table has {existing_rows} rows")
            
            # Drop the table
            logging.info("🗑️ Dropping existing technical_data_daily table...")
            cur.execute("DROP TABLE IF EXISTS technical_data_daily CASCADE")
            logging.info("✅ Successfully dropped technical_data_daily table")
            
            # Verify deletion
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'technical_data_daily'
                ) as table_exists
            """)
            result = cur.fetchone()
            still_exists = result['table_exists']
            
            if still_exists:
                logging.error("❌ Table still exists after DROP command!")
                return False
            else:
                logging.info("✅ Confirmed: technical_data_daily table has been deleted")
                return True
        else:
            logging.info("📋 technical_data_daily table does not exist (first run)")
            return True
            
    except Exception as e:
        logging.error(f"❌ Failed to delete existing table: {e}")
        import traceback
        logging.error(f"❌ Full traceback: {''.join(traceback.format_exc())}")
        return False

def create_technical_table(cur):
    """Create technical_data_daily table with comprehensive schema"""
    try:
        logging.info("🔧 Creating technical_data_daily table...")
        
        create_table_sql = """
        CREATE TABLE technical_data_daily (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10) NOT NULL,
            date DATE NOT NULL,
            
            -- Price data for reference
            open DECIMAL(12,4),
            high DECIMAL(12,4),
            low DECIMAL(12,4),
            close DECIMAL(12,4),
            volume BIGINT,
            
            -- Basic indicators
            rsi DECIMAL(8,4),
            mom DECIMAL(12,4),
            roc DECIMAL(8,4),
            
            -- Moving Averages
            sma_10 DECIMAL(12,4),
            sma_20 DECIMAL(12,4),
            sma_50 DECIMAL(12,4),
            sma_150 DECIMAL(12,4),
            sma_200 DECIMAL(12,4),
            ema_4 DECIMAL(12,4),
            ema_9 DECIMAL(12,4),
            ema_21 DECIMAL(12,4),
            
            -- MACD
            macd DECIMAL(12,6),
            macd_signal DECIMAL(12,6),
            macd_hist DECIMAL(12,6),
            
            -- Bollinger Bands
            bbands_lower DECIMAL(12,4),
            bbands_middle DECIMAL(12,4),
            bbands_upper DECIMAL(12,4),
            
            -- Other indicators
            atr DECIMAL(12,4),
            adx DECIMAL(8,4),
            
            -- Custom indicators
            td_sequential DECIMAL(8,2),
            td_combo DECIMAL(8,2),
            
            -- Metadata
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            
            UNIQUE(symbol, date)
        )
        """
        
        cur.execute(create_table_sql)
        logging.info("✅ Created technical_data_daily table")
        
        # Create indexes for performance
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_technical_daily_symbol ON technical_data_daily(symbol)",
            "CREATE INDEX IF NOT EXISTS idx_technical_daily_date ON technical_data_daily(date)",
            "CREATE INDEX IF NOT EXISTS idx_technical_daily_symbol_date ON technical_data_daily(symbol, date)",
            "CREATE INDEX IF NOT EXISTS idx_technical_daily_created_at ON technical_data_daily(created_at)"
        ]
        
        for index_sql in indexes:
            cur.execute(index_sql)
            index_name = index_sql.split(' ')[-1].split('(')[0]
            logging.info(f"✅ Created index: {index_name}")
        
        # Verify table creation
        cur.execute("""
            SELECT COUNT(*) as column_count 
            FROM information_schema.columns 
            WHERE table_name = 'technical_data_daily'
        """)
        result = cur.fetchone()
        column_count = result['column_count']
        logging.info(f"✅ Table created successfully with {column_count} columns")
        
        return True
        
    except Exception as e:
        logging.error(f"❌ Failed to create technical table: {e}")
        import traceback
        logging.error(f"❌ Full traceback: {''.join(traceback.format_exc())}")
        return False

def load_technicals_for_symbol(symbol, cur):
    """Load technical data for a single symbol with detailed logging"""
    try:
        logging.info(f"🔄 Processing symbol: {symbol}")
        
        # Fetch price data
        cur.execute("""
            SELECT date, open, high, low, close, volume
            FROM price_daily
            WHERE symbol = %s
            ORDER BY date ASC
        """, (symbol,))
        
        rows = cur.fetchall()
        if not rows:
            logging.warning(f"⚠️ No price data found for {symbol}")
            return 0
        
        logging.info(f"📊 Retrieved {len(rows)} price records for {symbol}")
        
        # Convert to DataFrame
        df = pd.DataFrame(rows)
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')
        
        logging.info(f"📊 Data range for {symbol}: {df.index.min()} to {df.index.max()}")
        
        # Calculate technical indicators
        df_tech = calculate_technicals_parallel(df)
        if df_tech is None:
            logging.warning(f"⚠️ Failed to calculate technicals for {symbol}")
            return 0
        
        # Prepare data for insertion
        df_tech = df_tech.reset_index()
        df_tech['symbol'] = symbol
        
        # Select columns for database (same as weekly/monthly)
        columns = [
            'symbol', 'date', 'open', 'high', 'low', 'close', 'volume',
            'rsi', 'mom', 'roc', 'sma_10', 'sma_20', 'sma_50', 'sma_150', 'sma_200',
            'ema_4', 'ema_9', 'ema_21', 'macd', 'macd_signal', 'macd_hist',
            'bbands_lower', 'bbands_middle', 'bbands_upper', 'atr', 'adx',
            'td_sequential', 'td_combo'
        ]
        
        # Filter to existing columns and replace NaN with None
        insert_data = []
        for _, row in df_tech.iterrows():
            row_data = []
            for col in columns:
                if col in df_tech.columns:
                    val = row[col]
                    row_data.append(None if pd.isna(val) else val)
                else:
                    row_data.append(None)
            insert_data.append(tuple(row_data))
        
        if not insert_data:
            logging.warning(f"⚠️ No data to insert for {symbol}")
            return 0
        
        # Insert data with conflict resolution
        insert_sql = f"""
            INSERT INTO technical_data_daily ({', '.join(columns)})
            VALUES ({', '.join(['%s'] * len(columns))})
            ON CONFLICT (symbol, date) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                rsi = EXCLUDED.rsi,
                mom = EXCLUDED.mom,
                roc = EXCLUDED.roc,
                sma_10 = EXCLUDED.sma_10,
                sma_20 = EXCLUDED.sma_20,
                sma_50 = EXCLUDED.sma_50,
                sma_150 = EXCLUDED.sma_150,
                sma_200 = EXCLUDED.sma_200,
                ema_4 = EXCLUDED.ema_4,
                ema_9 = EXCLUDED.ema_9,
                ema_21 = EXCLUDED.ema_21,
                macd = EXCLUDED.macd,
                macd_signal = EXCLUDED.macd_signal,
                macd_hist = EXCLUDED.macd_hist,
                bbands_lower = EXCLUDED.bbands_lower,
                bbands_middle = EXCLUDED.bbands_middle,
                bbands_upper = EXCLUDED.bbands_upper,
                atr = EXCLUDED.atr,
                adx = EXCLUDED.adx,
                td_sequential = EXCLUDED.td_sequential,
                td_combo = EXCLUDED.td_combo,
                updated_at = CURRENT_TIMESTAMP
        """
        
        execute_values(cur, insert_sql, insert_data, template=None, page_size=1000)
        
        logging.info(f"✅ Loaded {len(insert_data)} technical records for {symbol}")
        return len(insert_data)
        
    except Exception as e:
        logging.error(f"❌ Failed to load technicals for {symbol}: {e}")
        import traceback
        logging.error(f"❌ Full traceback: {''.join(traceback.format_exc())}")
        return 0

def get_db_config():
    """Get database configuration from AWS Secrets Manager"""
    try:
        # Get the secret ARN from environment variable
        secret_arn = os.environ.get('DB_SECRET_ARN')
        if not secret_arn:
            raise ValueError("DB_SECRET_ARN environment variable not set")
        
        # Create a Secrets Manager client
        session = boto3.session.Session()
        client = session.client(service_name='secretsmanager', region_name='us-east-1')
        
        # Get the secret value
        response = client.get_secret_value(SecretId=secret_arn)
        secret = json.loads(response['SecretString'])
        
        return {
            'host': secret['host'],
            'port': secret['port'],
            'dbname': secret['dbname'],
            'user': secret['username'],
            'password': secret['password']
        }
    except Exception as e:
        logging.error(f"❌ Failed to get database configuration: {e}")
        raise

if __name__ == "__main__":
    try:
        log_mem("startup")
        logging.info(f"🚀 Starting {SCRIPT_NAME}")

        # Connect to DB
        cfg = get_db_config()
        conn = psycopg2.connect(
            host=cfg["host"], port=cfg["port"],
            user=cfg["user"], password=cfg["password"],
            dbname=cfg["dbname"]
        )
        conn.autocommit = False
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Step 1: Validate prerequisites
        logging.info("🔍 Validating prerequisites...")
        if not validate_prerequisites(cur):
            logging.error("❌ Prerequisites not met for loading technical data")
            sys.exit(1)
        
        logging.info("✅ Prerequisites validation passed!")
        
        # Step 2: Delete existing table
        logging.info("🗑️ Deleting existing technical table...")
        if not delete_existing_table(cur):
            logging.error("❌ Failed to delete existing technical table")
            sys.exit(1)
        
        # Step 3: Create new table
        logging.info("🔧 Creating new technical table...")
        if not create_technical_table(cur):
            logging.error("❌ Failed to create technical table")
            sys.exit(1)
        
        conn.commit()
        logging.info("💾 Table creation committed to database")
        
        # Step 4: Get symbols to process (limit for testing)
        logging.info("📋 Getting symbols to process...")
        cur.execute("SELECT DISTINCT symbol FROM price_daily ORDER BY symbol LIMIT 50")  # Start with 50 for testing
        symbols = [row['symbol'] for row in cur.fetchall()]
        logging.info(f"📊 Found {len(symbols)} symbols to process")
        
        if not symbols:
            logging.warning("⚠️ No symbols found to process")
            sys.exit(0)
        
        # Step 5: Process symbols
        total_records = 0
        successful_symbols = 0
        failed_symbols = []
        
        for i, symbol in enumerate(symbols, 1):
            logging.info(f"🔄 Processing {symbol} ({i}/{len(symbols)})...")
            
            try:
                records_inserted = load_technicals_for_symbol(symbol, cur)
                if records_inserted > 0:
                    successful_symbols += 1
                    total_records += records_inserted
                else:
                    failed_symbols.append(symbol)
                    
                # Commit every 10 symbols to avoid long transactions
                if i % 10 == 0:
                    conn.commit()
                    logging.info(f"💾 Committed batch at symbol {i}")
                    log_mem(f"after_symbol_{i}")
                    
            except Exception as e:
                logging.error(f"❌ Failed to process {symbol}: {e}")
                failed_symbols.append(symbol)
        
        # Final commit
        conn.commit()
        
        # Final summary
        logging.info("=" * 60)
        logging.info("📊 PROCESSING SUMMARY")
        logging.info("=" * 60)
        logging.info(f"✅ Successfully processed: {successful_symbols}/{len(symbols)} symbols")
        logging.info(f"📊 Total technical records inserted: {total_records}")
        logging.info(f"❌ Failed symbols: {len(failed_symbols)}")
        
        if failed_symbols:
            logging.info(f"❌ Failed symbol list: {', '.join(failed_symbols[:10])}{'...' if len(failed_symbols) > 10 else ''}")
        
        # Verify final table state
        cur.execute("SELECT COUNT(*) as final_count FROM technical_data_daily")
        result = cur.fetchone()
        final_count = result['final_count']
        logging.info(f"📊 Final table count: {final_count} records")
        
        cur.execute("SELECT COUNT(DISTINCT symbol) as symbol_count FROM technical_data_daily")
        result = cur.fetchone()
        symbol_count = result['symbol_count']
        logging.info(f"📊 Final symbol count: {symbol_count} symbols")
        
        # Close connections
        cur.close()
        conn.close()
        
        log_mem("final")
        logging.info("🏁 loadtechnicalsdaily.py finished")
        logging.info("✅ Process completed successfully")
        logging.info(f"🏁 {SCRIPT_NAME} finished with exit code 0")
        
    except Exception as e:
        logging.error(f"❌ Fatal error in main: {e}")
        import traceback
        logging.error(f"❌ Full traceback: {''.join(traceback.format_exc())}")
        sys.exit(1)
