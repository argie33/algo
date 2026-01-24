#!/usr/bin/env python3
"""
Load Beta from yfinance - Simple direct beta loading from ticker.info
This is a quick loader to populate missing beta data (30-40% of stocks missing)
"""

import sys
import logging
import yfinance as yf
from db_helper import get_db_connection

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SCRIPT_NAME = "load_yfinance_beta.py"

def main():
    logger.info(f"🚀 Starting {SCRIPT_NAME} - Loading beta from yfinance")
    
    conn = get_db_connection(SCRIPT_NAME)
    if not conn:
        logger.error("❌ Failed to connect to database")
        sys.exit(1)
    
    try:
        cur = conn.cursor()
        
        # Create beta_yfinance table if not exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS beta_yfinance (
                symbol VARCHAR(50) PRIMARY KEY,
                beta DECIMAL(10, 4),
                source VARCHAR(50) DEFAULT 'yfinance',
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        logger.info("✅ beta_yfinance table ready")
        
        # Get all symbols from stock_symbols
        cur.execute("SELECT symbol FROM stock_symbols LIMIT 5312")
        symbols = [row[0] for row in cur.fetchall()]
        logger.info(f"📥 Loading beta for {len(symbols)} symbols...")
        
        loaded = 0
        skipped = 0
        errors = 0
        
        for i, symbol in enumerate(symbols):
            try:
                # Get beta from yfinance
                yf_symbol = symbol.replace('.', '-').upper()
                ticker = yf.Ticker(yf_symbol)
                beta = ticker.info.get('beta')
                
                if beta:
                    cur.execute("""
                        INSERT INTO beta_yfinance (symbol, beta)
                        VALUES (%s, %s)
                        ON CONFLICT (symbol) DO UPDATE SET beta = EXCLUDED.beta
                    """, (symbol, float(beta)))
                    loaded += 1
                else:
                    skipped += 1
                
                if (i + 1) % 100 == 0:
                    logger.info(f"  Processed {i + 1}/{len(symbols)} - Loaded: {loaded}, Skipped: {skipped}")
                    conn.commit()
                    
            except Exception as e:
                logger.warning(f"  Error loading {symbol}: {e}")
                errors += 1
        
        conn.commit()
        logger.info(f"✅ Beta loading complete:")
        logger.info(f"   Loaded: {loaded}/{len(symbols)} ({loaded*100/len(symbols):.1f}%)")
        logger.info(f"   Skipped (not available): {skipped}")
        logger.info(f"   Errors: {errors}")
        
        cur.close()
        sys.exit(0)
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()
