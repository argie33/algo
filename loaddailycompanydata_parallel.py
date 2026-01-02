#!/usr/bin/env python3
"""
Parallel Company Data Loader - Process a subset of stocks
Simplified version that doesn't import from main loader
"""
import sys
import subprocess

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 loaddailycompanydata_parallel.py <symbol_file>")
        sys.exit(1)
    
    symbol_file = sys.argv[1]
    loader_id = symbol_file.split('_')[-1].split('.')[0]
    
    # Read symbols from file
    try:
        with open(symbol_file, 'r') as f:
            symbols = [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"Failed to read symbol file {symbol_file}: {e}")
        sys.exit(1)
    
    print(f"Parallel Loader {loader_id}: Processing {len(symbols)} symbols")
    
    # Run the original loaddailycompanydata.py but with reduced delay
    # We'll temporarily patch the delay in memory
    import os
    os.chdir('/home/stocks/algo')
    
    # Create a modified loader that processes only our symbols
    # with reduced delay (1.5s instead of 3s)
    script = f"""
import sys; sys.path.insert(0, '/home/stocks/algo')
import time
import psycopg2
from psycopg2.extras import RealDictCursor
from loaddailycompanydata import load_all_realtime_data, get_db_config
import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Delayed start to stagger API requests
time.sleep({int(loader_id) * 0.5})

conn = psycopg2.connect(**get_db_config())
cur = conn.cursor(cursor_factory=RealDictCursor)

symbols = {symbols}
processed = 0
failed = 0

for symbol in symbols:
    try:
        stats = load_all_realtime_data(symbol, cur, conn)
        if stats:
            processed += 1
            logging.info(f"✅ {{symbol}}: {{stats}}")
        else:
            failed += 1
    except Exception as e:
        logging.error(f"Failed {{symbol}}: {{e}}")
        failed += 1
        conn.rollback()
    
    time.sleep(1.5)  # Reduced from 3s since we have 4 parallel loaders

logging.info(f"Loader {loader_id} done: {{processed}}/{{len(symbols)}} processed, {{failed}} failed")
cur.close()
conn.close()
"""
    
    # Execute the script
    result = subprocess.run([sys.executable, '-c', script], cwd='/home/stocks/algo')
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()
