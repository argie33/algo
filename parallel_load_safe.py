#!/usr/bin/env python3
"""Launch 2 safe parallel loaders for balanced speed+reliability"""
import subprocess
import os
import psycopg2
from datetime import datetime

def main():
    try:
        # Get stock list
        conn = psycopg2.connect(dbname="stocks", user="stocks")
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE (etf IS NULL OR etf != 'Y');")
        total = cur.fetchone()[0]
        cur.execute("SELECT symbol FROM stock_symbols WHERE (etf IS NULL OR etf != 'Y') ORDER BY symbol;")
        symbols = [r[0] for r in cur.fetchall()]
        cur.close()
        conn.close()
        
        # Split into 2 chunks
        chunk_size = (len(symbols) + 1) // 2
        chunks = [symbols[i:i+chunk_size] for i in range(0, len(symbols), chunk_size)]
        
        print(f"Total stocks: {total}")
        print(f"Running 2 safe parallel loaders ({len(chunks[0])} and {len(chunks[1])} stocks)")
        print(f"Started: {datetime.now()}")
        print("")
        
        # Create chunk files
        for i, chunk in enumerate(chunks):
            filename = f".parallel_chunk_{i}.txt"
            with open(filename, 'w') as f:
                for symbol in chunk:
                    f.write(symbol + "\n")
        
        # Start loaders
        processes = []
        for i in range(2):
            log_file = f"loaddailycompanydata_safe_parallel_{i}.log"
            cmd = f"python3 loaddailycompanydata_safe_parallel.py .parallel_chunk_{i}.txt > {log_file} 2>&1"
            print(f"Loader {i}: {len(chunks[i])} stocks → {log_file}")
            p = subprocess.Popen(cmd, shell=True)
            processes.append((i, p, log_file))
        
        print("")
        print("Monitor with:")
        print("  tail -f loaddailycompanydata_safe_parallel_0.log")
        print("  tail -f loaddailycompanydata_safe_parallel_1.log")
        print("")
        
        # Wait for completion
        print("Waiting for both loaders to complete...")
        results = []
        for i, p, log_file in processes:
            ret = p.wait()
            status = "✅ SUCCESS" if ret == 0 else f"⚠️  PARTIAL (code {ret})"
            print(f"Loader {i}: {status}")
            results.append((i, ret))
            # Cleanup
            try:
                os.remove(f".parallel_chunk_{i}.txt")
            except:
                pass
        
        print(f"\nCompleted: {datetime.now()}")
        
        # Verify data
        print("\n=== VERIFYING DATA ===")
        conn = psycopg2.connect(dbname="stocks", user="stocks")
        cur = conn.cursor()
        cur.execute("SELECT COUNT(DISTINCT symbol) FROM company_profile;")
        company_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(DISTINCT symbol) FROM positioning_metrics;")
        positioning_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM earnings;")
        earnings_count = cur.fetchone()[0]
        cur.close()
        conn.close()
        
        print(f"Company profiles: {company_count} stocks")
        print(f"Positioning metrics: {positioning_count} stocks")
        print(f"Earnings records: {earnings_count} rows")
        
        if company_count >= total * 0.95:  # At least 95% of stocks
            print(f"✅ Data load successful! ({company_count}/{total} stocks)")
            return 0
        else:
            print(f"⚠️  Incomplete data: only {company_count}/{total} stocks loaded")
            return 1
            
    except Exception as e:
        print(f"Error: {e}")
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
