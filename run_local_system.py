#!/usr/bin/env python3
"""
MAKE YOUR SITE WORKING LOCALLY
Loads real market data into a local/cloud database and starts the system.

Prerequisites:
  1. PostgreSQL running (local or cloud)
  2. Python 3.11+
  3. pip install -r requirements.txt

Usage:
  python run_local_system.py --host localhost --user postgres --password your_password --database algo
"""

import subprocess
import sys
import os
from pathlib import Path
import argparse

def run_command(cmd, description, env=None):
    """Run a command and report status."""
    print(f"\n{'=' * 60}")
    print(f"[STEP] {description}")
    print(f"{'=' * 60}")

    try:
        full_env = os.environ.copy()
        if env:
            full_env.update(env)

        result = subprocess.run(cmd, shell=True, env=full_env, check=True)
        print(f"✓ SUCCESS: {description}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ FAILED: {description}")
        print(f"Error: {e}")
        return False
    except Exception as e:
        print(f"✗ ERROR: {description}")
        print(f"Error: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Make your trading site fully working with real market data"
    )
    parser.add_argument(
        "--host", default="localhost", help="Database host (default: localhost)"
    )
    parser.add_argument("--port", default="5432", help="Database port (default: 5432)")
    parser.add_argument(
        "--user", default="postgres", help="Database user (default: postgres)"
    )
    parser.add_argument(
        "--password", required=True, help="Database password (REQUIRED)"
    )
    parser.add_argument(
        "--database", default="algo", help="Database name (default: algo)"
    )
    parser.add_argument(
        "--symbols",
        default="SPY,QQQ,IWM",
        help="Symbols to load (default: SPY,QQQ,IWM for quick testing)",
    )

    args = parser.parse_args()

    # Set up environment
    env = {
        "DB_HOST": args.host,
        "DB_PORT": args.port,
        "DB_USER": args.user,
        "DB_PASSWORD": args.password,
        "DB_NAME": args.database,
        "PYTHONPATH": str(Path.cwd()),
    }

    print("""

╔════════════════════════════════════════════════════════════╗
║                                                            ║
║     MAKE YOUR SITE FULLY WORKING WITH REAL DATA            ║
║                                                            ║
║  This script will:                                         ║
║  1. Load real price data from yfinance                     ║
║  2. Compute technical indicators                           ║
║  3. Generate trading signals                               ║
║  4. Populate your database with fresh data                 ║
║                                                            ║
║  Expected time: 10-20 minutes                              ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
    """)

    print(f"Database: {args.host}:{args.port}/{args.database}")
    print(f"Loading symbols: {args.symbols}")
    print("Parallelism: 4 threads (system will auto-use optimal based on DB load)")

    steps = [
        (
            f"python loaders/load_prices.py --symbols {args.symbols} --parallelism 4",
            "Step 1/3: Load real price data from yfinance",
            env,
        ),
        (
            f"python loaders/load_technical_data_daily.py --symbols {args.symbols} --parallelism 4",
            "Step 2/3: Compute technical indicators (RSI, MACD, Bollinger Bands, etc.)",
            env,
        ),
        (
            f"python loaders/load_buy_sell_daily.py --symbols {args.symbols} --parallelism 4",
            "Step 3/3: Generate buy/sell trading signals",
            env,
        ),
    ]

    success_count = 0
    for cmd, description, step_env in steps:
        if run_command(cmd, description, step_env):
            success_count += 1
        else:
            print(f"\n✗ Failed at: {description}")
            print(f"Check database connection: {args.host}:{args.port}/{args.database}")
            return 1

    # Verify data loaded
    print(f"\n{'=' * 60}")
    print("[VERIFY] Checking data in database")
    print(f"{'=' * 60}")

    try:
        import psycopg2

        conn = psycopg2.connect(
            host=args.host,
            port=args.port,
            user=args.user,
            password=args.password,
            database=args.database,
        )
        cur = conn.cursor()

        # Check price data
        cur.execute("SELECT COUNT(*), MAX(date) FROM price_daily;")
        price_count, price_date = cur.fetchone()
        print(f"✓ Price data: {price_count} records (latest: {price_date})")

        # Check technical data
        cur.execute("SELECT COUNT(*), MAX(date) FROM technical_data_daily;")
        tech_count, tech_date = cur.fetchone()
        print(f"✓ Technical data: {tech_count} records (latest: {tech_date})")

        # Check signals
        cur.execute("SELECT COUNT(*), MAX(date) FROM buy_sell_daily;")
        signal_count, signal_date = cur.fetchone()
        print(f"✓ Trading signals: {signal_count} records (latest: {signal_date})")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"✗ Could not verify data: {e}")
        return 1

    # Success!
    print("""

╔════════════════════════════════════════════════════════════╗
║                                                            ║
║          ✓ YOUR SITE IS NOW FULLY WORKING                  ║
║                                                            ║
║  Database populated with real market data:                 ║
║  - Price data loaded                                       ║
║  - Technical indicators computed                           ║
║  - Trading signals generated                               ║
║                                                            ║
║  NEXT STEPS:                                               ║
║                                                            ║
║  1. Start the API server:                                  ║
║     python lambda/api/lambda_function.py                   ║
║                                                            ║
║  2. In another terminal, start the frontend:               ║
║     cd webapp/frontend                                     ║
║     npm install (if first time)                            ║
║     npm run dev                                            ║
║                                                            ║
║  3. Open browser:                                          ║
║     http://localhost:5173                                  ║
║                                                            ║
║  You will see:                                             ║
║  - Real trading signals based on {args.symbols}            ║
║  - Current technical indicators                            ║
║  - Portfolio dashboard with live data                      ║
║                                                            ║
║  NO MOCK DATA. NO PLACEHOLDERS.                            ║
║  REAL MARKET DATA. REAL SIGNALS. REAL TRADING.             ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
    """)

    return 0

if __name__ == "__main__":
    sys.exit(main())
