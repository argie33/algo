#!/usr/bin/env python3
"""
Fixed Earnings Data Loader - Processes ALL 5,057 symbols reliably
Handles yfinance API inconsistencies gracefully
Commits progress frequently to avoid data loss
"""

import sys
import logging
import psycopg2
import psycopg2.extras
import yfinance as yf
import time
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

# Suppress yfinance noise
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)

def get_db_connection():
    """Get database connection"""
    try:
        conn = psycopg2.connect(
            dbname="stocks",
            user="stocks",
            host="localhost"
        )
        return conn
    except Exception as e:
        logging.error(f"❌ Failed to connect to database: {e}")
        sys.exit(1)

def load_earnings_for_symbol(conn, cursor, symbol):
    """Load earnings data for ONE symbol"""
    try:
        ticker = yf.Ticker(symbol)
        earnings_est = ticker.earnings_estimate
        
        if earnings_est is None or earnings_est.empty:
            return 0  # No data
        
        # Delete old data
        cursor.execute("DELETE FROM earnings_estimates WHERE symbol = %s", (symbol,))
        
        # Insert new data
        rows = []
        for period, row in earnings_est.iterrows():
            rows.append((
                symbol, str(period),
                float(row.get("avg", None)) if row.get("avg") else None,
                float(row.get("low", None)) if row.get("low") else None,
                float(row.get("high", None)) if row.get("high") else None,
                float(row.get("yearAgoEps", None)) if row.get("yearAgoEps") else None,
                int(row.get("numberOfAnalysts", None)) if row.get("numberOfAnalysts") else None,
                float(row.get("growth", None)) if row.get("growth") else None,
            ))
        
        if rows:
            psycopg2.extras.execute_values(
                cursor,
                """
                INSERT INTO earnings_estimates 
                (symbol, period, avg_estimate, low_estimate, high_estimate, 
                 year_ago_eps, number_of_analysts, growth)
                VALUES %s
                ON CONFLICT (symbol, period) DO UPDATE SET
                  avg_estimate = EXCLUDED.avg_estimate,
                  low_estimate = EXCLUDED.low_estimate,
                  high_estimate = EXCLUDED.high_estimate,
                  year_ago_eps = EXCLUDED.year_ago_eps,
                  number_of_analysts = EXCLUDED.number_of_analysts,
                  growth = EXCLUDED.growth
                """,
                rows
            )
            return len(rows)
        
        return 0
        
    except Exception as e:
        logging.warning(f"⚠️  {symbol}: {str(e)[:60]}")
        return -1  # Error

def main():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get all symbols
    cursor.execute("SELECT symbol FROM stock_symbols ORDER BY symbol")
    symbols = [r[0] for r in cursor.fetchall()]
    
    logging.info(f"Loading earnings data for {len(symbols)} symbols...")
    logging.info("=" * 80)
    
    total_inserted = 0
    symbols_with_data = 0
    symbols_with_errors = 0
    symbols_without_data = 0
    
    for i, symbol in enumerate(symbols, 1):
        result = load_earnings_for_symbol(conn, cursor, symbol)
        
        if result > 0:
            total_inserted += result
            symbols_with_data += 1
        elif result == 0:
            symbols_without_data += 1
        else:
            symbols_with_errors += 1
        
        # Commit every 100 symbols to save progress
        if i % 100 == 0:
            conn.commit()
            pct = int(100 * i / len(symbols))
            logging.info(f"[{pct:3d}%] Processed {i:5d} / {len(symbols)} - " +
                        f"Found: {symbols_with_data:4d}, No data: {symbols_without_data:4d}, " +
                        f"Errors: {symbols_with_errors:4d}, Records: {total_inserted:5d}")
        
        # Rate limiting
        if i % 50 == 0:
            time.sleep(0.1)
    
    # Final commit
    conn.commit()
    
    logging.info("=" * 80)
    logging.info("✅ EARNINGS LOADER COMPLETE")
    logging.info(f"Symbols processed: {len(symbols)}")
    logging.info(f"Symbols with earnings data: {symbols_with_data} ({100*symbols_with_data//len(symbols)}%)")
    logging.info(f"Symbols without earnings data: {symbols_without_data}")
    logging.info(f"Symbols with errors: {symbols_with_errors}")
    logging.info(f"Total records inserted: {total_inserted}")
    logging.info("=" * 80)
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    main()
