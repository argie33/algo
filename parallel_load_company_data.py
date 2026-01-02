#!/usr/bin/env python3
"""
Parallel Company Data Loader - Run 4 instances simultaneously
Each instance processes a different subset of stocks to 4x speedup
"""
import sys
import subprocess
import os
from datetime import datetime

def main():
    # Get total stocks
    import psycopg2

    try:
        # Use socket connection (peer auth) like the original loader
        conn = psycopg2.connect(
            dbname="stocks",
            user="stocks"
        )
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE (etf IS NULL OR etf != 'Y');")
        total_stocks = cur.fetchone()[0]
        cur.close()
        conn.close()
        
        print(f"Total stocks: {total_stocks}")
        
        # Get stock list
        conn = psycopg2.connect(
            dbname="stocks",
            user="stocks"
        )
        cur = conn.cursor()
        cur.execute("SELECT symbol FROM stock_symbols WHERE (etf IS NULL OR etf != 'Y') ORDER BY symbol;")
        symbols = [r[0] for r in cur.fetchall()]
        cur.close()
        conn.close()
        
        # Split into 4 chunks
        chunk_size = (len(symbols) + 3) // 4
        chunks = [symbols[i:i+chunk_size] for i in range(0, len(symbols), chunk_size)]
        
        print(f"Running 4 parallel loaders ({chunk_size} stocks each)")
        print(f"Started: {datetime.now()}")
        print("")
        
        # Create temporary chunk files
        chunk_files = []
        for i, chunk in enumerate(chunks):
            filename = f".parallel_chunk_{i}.txt"
            with open(filename, 'w') as f:
                for symbol in chunk:
                    f.write(symbol + "\n")
            chunk_files.append((i, filename))
        
        # Start parallel loaders
        processes = []
        for i, chunk_file in chunk_files:
            log_file = f"loaddailycompanydata_parallel_{i}.log"
            cmd = f"python3 loaddailycompanydata_parallel.py {chunk_file} > {log_file} 2>&1"
            print(f"Loader {i}: {len(chunks[i])} stocks -> {log_file}")
            p = subprocess.Popen(cmd, shell=True)
            processes.append((i, p, log_file, chunk_file))
        
        print("")
        print("Monitor progress with:")
        for i in range(len(chunks)):
            print(f"  tail loaddailycompanydata_parallel_{i}.log")
        
        # Wait for all to complete
        print("")
        print("Waiting for all loaders to complete...")
        failed = []
        for i, p, log_file, chunk_file in processes:
            ret = p.wait()
            status = "✅ SUCCESS" if ret == 0 else f"❌ FAILED (code {ret})"
            print(f"Loader {i}: {status}")
            if ret != 0:
                failed.append(i)
            # Clean up chunk file
            try:
                os.remove(chunk_file)
            except:
                pass
        
        print(f"\nCompleted: {datetime.now()}")
        
        if failed:
            print(f"❌ {len(failed)} loaders failed: {failed}")
            sys.exit(1)
        else:
            print("✅ All parallel loaders completed successfully!")
            sys.exit(0)
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
