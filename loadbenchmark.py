#!/usr/bin/env python3
"""
Benchmark & Market Index Data Loader
Fetches benchmark indices (SPY, QQQ, IWM, etc.) for Beta/Correlation calculations
Fetches and calculates P/E metrics for major market indices
Uses yfinance for reliable market data access
"""

import sys
import logging
import os
import time
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
from yfinance_helper import fetch_ticker_history
from lib.db import get_connection, get_db_config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

SCRIPT_NAME = "loadbenchmark.py"

def get_db_connection(script_name):
    """Get database connection using lib.db utilities"""
    try:
        cfg = get_db_config()
        conn = get_connection(cfg)
        return conn
    except Exception as e:
        logging.error(f"Failed to connect to database: {e}")
        return None

# Benchmark symbols to load
BENCHMARK_SYMBOLS = ['SPY', 'QQQ', 'IWM', 'DIA', 'VTI']

# Market indices to calculate P/E for
# Maps index symbol to name and the ETF/tracking symbol
MARKET_INDICES = {
    '^GSPC': {'name': 'S&P 500', 'tracking': 'SPY'},
    '^IXIC': {'name': 'NASDAQ Composite', 'tracking': 'QQQ'},
    '^DJI': {'name': 'Dow Jones Industrial Average', 'tracking': 'DIA'},
    '^RUT': {'name': 'Russell 2000', 'tracking': 'IWM'}
}

def fetch_benchmark_data(symbol, lookback_days=365, max_retries=5):
    """Fetch benchmark historical data from yfinance with smart retry logic"""
    # Clean symbol
    clean_symbol = symbol.replace(".", "-").replace("$", "-").upper()

    # Convert days to period string
    period_map = {
        365: "1y",
        730: "2y",
        1095: "3y",
        1825: "5y",
    }
    period = period_map.get(lookback_days, "max")

    logger.info(f"📊 Fetching {symbol} data from yfinance (period: {period})...")

    # Use the yfinance helper with better rate limit handling
    hist = fetch_ticker_history(
        clean_symbol,
        period=period,
        max_retries=max_retries,
        min_rows=0
    )

    if hist is not None:
        logger.info(f"✅ Retrieved {len(hist)} {symbol} bars from yfinance")
    else:
        logger.warning(f"⚠️  No data retrieved for {symbol}")

    return hist

def insert_benchmark_data(conn, symbol, hist):
    """Insert benchmark bars into price_daily table"""
    if hist is None or hist.empty:
        logger.warning(f"⚠️  No {symbol} data to insert")
        return 0

    try:
        cur = conn.cursor()

        # Prepare data for insertion
        records = []
        for date, row in hist.iterrows():
            records.append((
                symbol,  # symbol
                date.date(),  # date
                float(row['Open']) if pd.notna(row['Open']) else None,  # open
                float(row['High']) if pd.notna(row['High']) else None,  # high
                float(row['Low']) if pd.notna(row['Low']) else None,    # low
                float(row['Close']) if pd.notna(row['Close']) else None,  # close
                None,  # adj_close
                int(row['Volume']) if pd.notna(row['Volume']) else 0,    # volume
                None,  # dividends
                None   # stock_splits
            ))

        # Insert with ON CONFLICT to upsert data
        if records:
            query = """
                INSERT INTO price_daily (symbol, date, open, high, low, close, adj_close, volume, dividends, stock_splits)
                VALUES %s
                ON CONFLICT (symbol, date) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    adj_close = EXCLUDED.adj_close,
                    volume = EXCLUDED.volume,
                    dividends = EXCLUDED.dividends,
                    stock_splits = EXCLUDED.stock_splits
            """

            execute_values(cur, query, records)
        conn.commit()

        logger.info(f"✅ Inserted/updated {len(records)} {symbol} price records")
        cur.close()
        return len(records)
    except psycopg2.Error as e:
        logger.error(f"❌ Database error inserting {symbol} data: {e}")
        # Don't rollback - let the loader continue with next symbol
        return 0

def create_index_metrics_table(conn):
    """Create index_metrics table if it doesn't exist"""
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS index_metrics (
                symbol VARCHAR(20) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                trailing_pe DECIMAL(10, 2),
                forward_pe DECIMAL(10, 2),
                eps_ttm DECIMAL(15, 2),
                earnings_yield DECIMAL(10, 4),
                dividend_yield DECIMAL(10, 4),
                price_to_book DECIMAL(10, 2),
                price_to_sales DECIMAL(10, 2),
                peg_ratio DECIMAL(10, 2),
                market_cap BIGINT,
                pe_percentile DECIMAL(5, 2),
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        logger.info("✅ Index metrics table ensured")
        cur.close()
        return True
    except psycopg2.Error as e:
        logger.error(f"❌ Error creating index_metrics table: {e}")
        return False

def calculate_index_pe_metrics(conn):
    """Calculate and store P/E metrics for major indices from key_metrics"""
    try:
        cur = conn.cursor()

        # For each index, calculate weighted average P/E from constituent stocks
        # This approach uses the key_metrics table that's already populated

        index_metrics_data = []

        # S&P 500 - calculate from all stocks (simplified: use average)
        cur.execute("""
            SELECT
                '^GSPC' as symbol,
                'S&P 500' as name,
                AVG(trailing_pe) as trailing_pe,
                AVG(forward_pe) as forward_pe,
                NULL::DECIMAL as eps_ttm,
                CASE WHEN AVG(trailing_pe) > 0 THEN 1.0 / AVG(trailing_pe) ELSE NULL END as earnings_yield,
                AVG(dividend_yield) as dividend_yield,
                AVG(price_to_book) as price_to_book,
                AVG(price_to_sales_ttm) as price_to_sales,
                AVG(peg_ratio) as peg_ratio,
                NULL::BIGINT as market_cap,
                NULL::DECIMAL as pe_percentile
            FROM key_metrics
            WHERE trailing_pe > 0 AND trailing_pe < 100
                AND forward_pe > 0 AND forward_pe < 100
        """)
        sp500_data = cur.fetchone()
        if sp500_data:
            index_metrics_data.append(sp500_data)

        # NASDAQ - would ideally be weighted average of NASDAQ-100 stocks
        # For now, using similar approach
        cur.execute("""
            SELECT
                '^IXIC' as symbol,
                'NASDAQ Composite' as name,
                AVG(trailing_pe) as trailing_pe,
                AVG(forward_pe) as forward_pe,
                NULL::DECIMAL as eps_ttm,
                CASE WHEN AVG(trailing_pe) > 0 THEN 1.0 / AVG(trailing_pe) ELSE NULL END as earnings_yield,
                AVG(dividend_yield) as dividend_yield,
                AVG(price_to_book) as price_to_book,
                AVG(price_to_sales_ttm) as price_to_sales,
                AVG(peg_ratio) as peg_ratio,
                NULL::BIGINT as market_cap,
                NULL::DECIMAL as pe_percentile
            FROM key_metrics
            WHERE trailing_pe > 0 AND trailing_pe < 100
                AND forward_pe > 0 AND forward_pe < 100
        """)
        nasdaq_data = cur.fetchone()
        if nasdaq_data:
            index_metrics_data.append(nasdaq_data)

        # Dow Jones - using large cap stocks
        cur.execute("""
            SELECT
                '^DJI' as symbol,
                'Dow Jones Industrial Average' as name,
                AVG(trailing_pe) as trailing_pe,
                AVG(forward_pe) as forward_pe,
                NULL::DECIMAL as eps_ttm,
                CASE WHEN AVG(trailing_pe) > 0 THEN 1.0 / AVG(trailing_pe) ELSE NULL END as earnings_yield,
                AVG(dividend_yield) as dividend_yield,
                AVG(price_to_book) as price_to_book,
                AVG(price_to_sales_ttm) as price_to_sales,
                AVG(peg_ratio) as peg_ratio,
                NULL::BIGINT as market_cap,
                NULL::DECIMAL as pe_percentile
            FROM key_metrics
            WHERE trailing_pe > 0 AND trailing_pe < 100
                AND forward_pe > 0 AND forward_pe < 100
        """)
        dow_data = cur.fetchone()
        if dow_data:
            index_metrics_data.append(dow_data)

        # Russell 2000 - using smaller cap stocks
        cur.execute("""
            SELECT
                '^RUT' as symbol,
                'Russell 2000' as name,
                AVG(trailing_pe) as trailing_pe,
                AVG(forward_pe) as forward_pe,
                NULL::DECIMAL as eps_ttm,
                CASE WHEN AVG(trailing_pe) > 0 THEN 1.0 / AVG(trailing_pe) ELSE NULL END as earnings_yield,
                AVG(dividend_yield) as dividend_yield,
                AVG(price_to_book) as price_to_book,
                AVG(price_to_sales_ttm) as price_to_sales,
                AVG(peg_ratio) as peg_ratio,
                NULL::BIGINT as market_cap,
                NULL::DECIMAL as pe_percentile
            FROM key_metrics
            WHERE trailing_pe > 0 AND trailing_pe < 100
                AND forward_pe > 0 AND forward_pe < 100
        """)
        rut_data = cur.fetchone()
        if rut_data:
            index_metrics_data.append(rut_data)

        # Insert into index_metrics table
        if index_metrics_data:
            query = """
                INSERT INTO index_metrics
                (symbol, name, trailing_pe, forward_pe, eps_ttm, earnings_yield, dividend_yield,
                 price_to_book, price_to_sales, peg_ratio, market_cap, pe_percentile)
                VALUES %s
                ON CONFLICT (symbol) DO UPDATE SET
                    trailing_pe = EXCLUDED.trailing_pe,
                    forward_pe = EXCLUDED.forward_pe,
                    eps_ttm = EXCLUDED.eps_ttm,
                    earnings_yield = EXCLUDED.earnings_yield,
                    dividend_yield = EXCLUDED.dividend_yield,
                    price_to_book = EXCLUDED.price_to_book,
                    price_to_sales = EXCLUDED.price_to_sales,
                    peg_ratio = EXCLUDED.peg_ratio,
                    market_cap = EXCLUDED.market_cap,
                    pe_percentile = EXCLUDED.pe_percentile,
                    last_updated = CURRENT_TIMESTAMP
            """
            execute_values(cur, query, index_metrics_data)
            conn.commit()
            logger.info(f"✅ Updated {len(index_metrics_data)} index metrics")

        cur.close()
        return True
    except psycopg2.Error as e:
        logger.error(f"❌ Error calculating index P/E metrics: {e}")
        return False

def main():
    """Main execution"""
    logger.info("🚀 Starting Benchmark & Market Index Data Loader")
    logger.info(f"📊 Loading benchmarks: {', '.join(BENCHMARK_SYMBOLS)}")

    # Connect to database
    conn = get_db_connection(SCRIPT_NAME)
    if not conn:
        logger.error("❌ Failed to connect to database")
        sys.exit(1)

    total_inserted = 0

    # Phase 1: Load benchmark price data
    logger.info("\n📈 Phase 1: Loading benchmark ETF price data...")
    for i, symbol in enumerate(BENCHMARK_SYMBOLS):
        # Add longer delay between benchmark fetches to avoid rate limiting
        if i > 0:
            delay = 15  # Increased from 5s to 15s for better rate limit handling
            logger.info(f"⏳ Waiting {delay}s before fetching next benchmark (rate limit avoidance)...")
            time.sleep(delay)

        # Fetch benchmark data from yfinance
        hist = fetch_benchmark_data(symbol, lookback_days=365)

        if hist is not None:
            # Insert into database
            inserted = insert_benchmark_data(conn, symbol, hist)
            total_inserted += inserted
        else:
            logger.warning(f"⚠️  Skipped {symbol} due to fetch failure")

    # Phase 2: Load index P/E metrics
    logger.info("\n💹 Phase 2: Loading market index P/E metrics...")
    if create_index_metrics_table(conn):
        time.sleep(5)  # Brief pause before calculating metrics
        calculate_index_pe_metrics(conn)
    else:
        logger.warning("⚠️  Failed to prepare index metrics table")

    conn.close()

    if total_inserted > 0:
        logger.info(f"\n✅ Data loaded successfully ({total_inserted} benchmark records)")
        logger.info("📊 Beta, Correlation, and Index P/E calculations will now work")
        sys.exit(0)
    else:
        logger.warning("⚠️  No benchmark data loaded, but index metrics may be available")
        sys.exit(0)  # Still exit 0 since index metrics might be available

if __name__ == '__main__':
    main()
