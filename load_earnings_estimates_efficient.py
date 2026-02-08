#!/usr/bin/env python3
"""
Load earnings estimates from yfinance for all symbols efficiently.
This complements the earnings history loader.
"""
import os
import sys
import logging
import time
import yfinance as yf
import psycopg2
from psycopg2.extras import execute_values

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

def get_db_config():
    """Get database configuration"""
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", 5432)),
        "user": os.environ.get("DB_USER", "stocks"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "dbname": os.environ.get("DB_NAME", "stocks")
    }

def load_earnings_estimates(symbols):
    """Load earnings estimates for all symbols"""
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
    )
    cur = conn.cursor()
    
    total = len(symbols)
    processed = 0
    failed = 0
    
    CHUNK_SIZE = 20
    batches = (total + CHUNK_SIZE - 1) // CHUNK_SIZE
    
    for batch_idx in range(batches):
        batch = symbols[batch_idx*CHUNK_SIZE:(batch_idx+1)*CHUNK_SIZE]
        logging.info(f"Processing batch {batch_idx+1}/{batches} ({len(batch)} symbols)")
        
        for symbol in batch:
            try:
                ticker = yf.Ticker(symbol)
                
                # Try to get earnings estimate data
                eps_estimate = ticker.eps_trend
                if eps_estimate is not None and not eps_estimate.empty:
                    estimate_data = []
                    for period, row in eps_estimate.iterrows():
                        avg_est = row.get('avg_estimate')
                        low_est = row.get('low_estimate')
                        high_est = row.get('high_estimate')
                        year_ago = row.get('year_ago_eps')
                        num_analysts = row.get('number_of_analysts')
                        growth = row.get('growth')
                        
                        if avg_est is not None:
                            estimate_data.append((
                                symbol,
                                str(period),
                                float(avg_est) if avg_est else None,
                                float(low_est) if low_est else None,
                                float(high_est) if high_est else None,
                                float(year_ago) if year_ago else None,
                                int(num_analysts) if num_analysts else None,
                                float(growth) if growth else None,
                            ))
                    
                    if estimate_data:
                        execute_values(cur, """
                            INSERT INTO earnings_estimates (
                                symbol, period, avg_estimate, low_estimate,
                                high_estimate, year_ago_eps, number_of_analysts, growth
                            ) VALUES %s
                            ON CONFLICT (symbol, period) DO UPDATE SET
                                avg_estimate = EXCLUDED.avg_estimate,
                                low_estimate = EXCLUDED.low_estimate,
                                high_estimate = EXCLUDED.high_estimate,
                                year_ago_eps = EXCLUDED.year_ago_eps,
                                number_of_analysts = EXCLUDED.number_of_analysts,
                                growth = EXCLUDED.growth,
                                fetched_at = CURRENT_TIMESTAMP
                        """, estimate_data)
                        conn.commit()
                        processed += 1
                        logging.info(f"✓ {symbol}: {len(estimate_data)} estimate records")
                else:
                    failed += 1
            except Exception as e:
                logging.debug(f"✗ {symbol}: {e}")
                failed += 1
            
            time.sleep(0.05)
    
    # Update last_updated
    cur.execute("""
        INSERT INTO last_updated (script_name, last_run)
        VALUES ('load_earnings_estimates_efficient.py', NOW())
        ON CONFLICT (script_name) DO UPDATE
        SET last_run = EXCLUDED.last_run;
    """)
    conn.commit()
    
    cur.close()
    conn.close()
    
    logging.info(f"Earnings Estimates — total: {total}, processed: {processed}, failed: {failed}")

if __name__ == "__main__":
    # Get all symbols
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
    )
    cur = conn.cursor()
    cur.execute("SELECT symbol FROM stock_symbols ORDER BY symbol;")
    symbols = [r[0] for r in cur.fetchall()]
    cur.close()
    conn.close()
    
    load_earnings_estimates(symbols)
