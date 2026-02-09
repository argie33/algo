#!/usr/bin/env python3
"""Complete Earnings Loader - All 5,057 symbols with proper rate limiting"""

import sys, logging, psycopg2, psycopg2.extras, yfinance as yf, time, math

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s", stream=sys.stdout)
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)

def safe_float(val):
    try:
        if val is None or (isinstance(val, float) and math.isnan(val)):
            return None
        return float(val)
    except:
        return None

def safe_int(val):
    try:
        if val is None or (isinstance(val, float) and math.isnan(val)):
            return None
        return int(val) if isinstance(val, int) else int(float(val))
    except:
        return None

conn = psycopg2.connect(dbname="stocks", user="stocks", host="localhost")
cursor = conn.cursor()
cursor.execute("SELECT symbol FROM stock_symbols ORDER BY symbol")
symbols = [r[0] for r in cursor.fetchall()]

logging.info(f"Loading earnings for {len(symbols)} symbols...")

stats = {"found": 0, "nodata": 0, "errors": 0, "records": 0}

for i, symbol in enumerate(symbols, 1):
    try:
        ticker = yf.Ticker(symbol)
        est = ticker.earnings_estimate
        
        if est is None or est.empty:
            stats["nodata"] += 1
        else:
            cursor.execute("DELETE FROM earnings_estimates WHERE symbol = %s", (symbol,))
            rows = [
                (symbol, str(p), safe_float(est.loc[p, "avg"]), safe_float(est.loc[p, "low"]), 
                 safe_float(est.loc[p, "high"]), safe_float(est.loc[p, "yearAgoEps"]), 
                 safe_int(est.loc[p, "numberOfAnalysts"]), safe_float(est.loc[p, "growth"]))
                for p in est.index
            ]
            if rows:
                psycopg2.extras.execute_values(cursor,
                    "INSERT INTO earnings_estimates (symbol,period,avg_estimate,low_estimate,high_estimate,year_ago_eps,number_of_analysts,growth) VALUES %s ON CONFLICT (symbol,period) DO UPDATE SET avg_estimate=EXCLUDED.avg_estimate,low_estimate=EXCLUDED.low_estimate,high_estimate=EXCLUDED.high_estimate,year_ago_eps=EXCLUDED.year_ago_eps,number_of_analysts=EXCLUDED.number_of_analysts,growth=EXCLUDED.growth",
                    rows)
                stats["found"] += 1
                stats["records"] += len(rows)
        
        if i % 50 == 0:
            conn.commit()
        
        if i % 100 == 0:
            pct = i*100//len(symbols)
            logging.info(f"[{pct:3d}%] {i:5d}/{len(symbols)} | Found:{stats['found']:4d} | Records:{stats['records']:5d}")
        
        time.sleep(0.2)  # Rate limiting
        
    except Exception as e:
        stats["errors"] += 1
        if i % 100 == 0:
            logging.warning(f"Error on {symbol}: {str(e)[:40]}")

conn.commit()
logging.info("="*60)
logging.info(f"✅ COMPLETE - Symbols:{stats['found']} ({100*stats['found']//len(symbols)}%) | Records:{stats['records']}")
logging.info("="*60)
cursor.close()
conn.close()
