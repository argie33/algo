#!/usr/bin/env python3
"""
Test base pattern detection on sample symbols
Validates accuracy before full run
"""
import sys
import pandas as pd
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
import os

# Load env
env_path = Path('.env.local')
load_dotenv(env_path)

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 5432)),
        user=os.getenv('DB_USER', 'stocks'),
        password=os.getenv('DB_PASSWORD', ''),
        dbname=os.getenv('DB_NAME', 'stocks')
    )

def test_detection():
    """Test pattern detection on sample data"""

    # Import the detection functions from loadbuyselldaily
    import importlib.util
    spec = importlib.util.spec_from_file_location("loadbuyselldaily", "loadbuyselldaily.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    test_symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'AMZN', 'NVDA']

    conn = get_db_connection()
    cur = conn.cursor()

    print("=" * 70)
    print("BASE PATTERN DETECTION TEST")
    print("=" * 70)
    print(f"\nTesting on {len(test_symbols)} symbols: {', '.join(test_symbols)}\n")

    total_tested = 0
    pattern_counts = {}
    confidence_scores = []

    for symbol in test_symbols:
        print(f"Testing {symbol}...", end=' ', flush=True)

        try:
            # Get recent daily data
            cur.execute("""
                SELECT date, open, high, low, close, volume
                FROM price_daily
                WHERE symbol = %s
                AND date >= CURRENT_DATE - INTERVAL '400 days'
                ORDER BY date ASC
            """, (symbol,))

            rows = cur.fetchall()
            if len(rows) < 65:
                print(f"SKIP (only {len(rows)} days of data)")
                continue

            # Create dataframe
            df = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')

            # Test detection at current date (last row)
            current_idx = len(df) - 1

            base_type, confidence = module.identify_base_pattern(df, current_idx, lookback_days=65)

            if base_type:
                pattern_counts[base_type] = pattern_counts.get(base_type, 0) + 1
                confidence_scores.append(confidence)
                print(f"FOUND: {base_type} ({confidence:.0f}%)")
                total_tested += 1
            else:
                print("no pattern")
                total_tested += 1

        except Exception as e:
            print(f"ERROR: {str(e)[:50]}")

    # Summary
    print("\n" + "=" * 70)
    print("TEST RESULTS")
    print("=" * 70)
    print(f"Symbols tested: {total_tested}")
    print(f"Patterns detected: {sum(pattern_counts.values())}")
    print(f"Detection rate: {sum(pattern_counts.values())/max(total_tested,1)*100:.1f}%\n")

    if pattern_counts:
        print("Patterns found:")
        for ptype, count in sorted(pattern_counts.items()):
            print(f"  - {ptype}: {count}")

    if confidence_scores:
        print(f"\nConfidence scores:")
        print(f"  - Average: {sum(confidence_scores)/len(confidence_scores):.1f}%")
        print(f"  - Min: {min(confidence_scores):.1f}%")
        print(f"  - Max: {max(confidence_scores):.1f}%")
        print(f"  - Count: {len(confidence_scores)}")

    print("\n[OK] Test complete. Ready for full run.\n")

    conn.close()

if __name__ == "__main__":
    try:
        test_detection()
    except Exception as e:
        print(f"Test failed: {e}")
        sys.exit(1)
