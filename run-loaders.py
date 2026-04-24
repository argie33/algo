#!/usr/bin/env python3
"""
Master Loader Orchestrator - Run AWS loaders locally with proper sequencing

This script runs the existing AWS-integrated loaders in the correct order locally,
testing them before pushing to AWS. Handles:
- Schema initialization
- Sequential execution with dependencies
- Rate limiting between loaders
- Progress tracking
- Error handling (continue on failure, don't lose data)
"""

import os
import sys
import subprocess
import time
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Fix Windows encoding issues
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Load environment
env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

# Configuration
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "stocks")
DB_NAME = os.getenv("DB_NAME", "stocks")

PROGRESS_FILE = Path(__file__).parent / ".loader-progress.json"
RATE_LIMIT_SECONDS = 2  # Delay between loaders to avoid overloading

# Loaders in dependency order (must run in this order)
LOADERS = [
    # Phase 1: Foundation (no dependencies)
    {
        "name": "Stock Symbols",
        "script": "loadstocksymbols.py",
        "critical": True,
        "description": "Load NASDAQ/NYSE symbol list",
    },
    # Phase 2: Price Data (depends on symbols)
    {
        "name": "Price Daily",
        "script": "loadpricedaily.py",
        "critical": True,
        "description": "Load daily price data",
    },
    # Phase 3: Company Data (depends on symbols)
    {
        "name": "Daily Company Data",
        "script": "loaddailycompanydata.py",
        "critical": False,
        "description": "Load company info, positioning, earnings",
    },
    # Phase 4: Financial Statements (depends on symbols)
    {
        "name": "Annual Income Statement",
        "script": "loadannualincomestatement.py",
        "critical": False,
        "description": "Load annual income statements",
    },
    {
        "name": "Annual Balance Sheet",
        "script": "loadannualbalancesheet.py",
        "critical": False,
        "description": "Load annual balance sheets",
    },
    {
        "name": "Annual Cash Flow",
        "script": "loadannualcashflow.py",
        "critical": False,
        "description": "Load annual cash flow",
    },
    # Phase 5: Technical/Sentiment (depends on prices)
    {
        "name": "Technical Indicators",
        "script": "loadtechnicalindicators.py",
        "critical": False,
        "description": "Load technical indicators",
    },
    {
        "name": "Sentiment Data",
        "script": "loadsentiment.py",
        "critical": False,
        "description": "Load sentiment analysis",
    },
    {
        "name": "Analyst Sentiment",
        "script": "loadanalystsentiment.py",
        "critical": False,
        "description": "Load analyst sentiment ratings",
    },
    {
        "name": "Fear & Greed Index",
        "script": "loadfeargreed.py",
        "critical": False,
        "description": "Load CNN Fear & Greed Index",
    },
    {
        "name": "AAII Sentiment",
        "script": "loadaaiidata.py",
        "critical": False,
        "description": "Load AAII Sentiment Survey data",
    },
    {
        "name": "NAAIM Exposure",
        "script": "loadnaaim.py",
        "critical": False,
        "description": "Load NAAIM Manager Exposure Index",
    },
    # Phase 6: Buy/Sell Signals (depends on prices + technicals)
    {
        "name": "Buy/Sell Daily",
        "script": "loadbuyselldaily.py",
        "critical": False,
        "description": "Load daily buy/sell signals",
    },
]

def load_progress():
    """Load progress from file"""
    if PROGRESS_FILE.exists():
        try:
            with open(PROGRESS_FILE) as f:
                return json.load(f)
        except:
            pass
    return {"completed": [], "failed": []}

def save_progress(progress):
    """Save progress to file"""
    try:
        with open(PROGRESS_FILE, 'w') as f:
            json.dump(progress, f, indent=2)
    except Exception as e:
        print(f"⚠️  Could not save progress: {e}")

def print_header(title):
    """Print section header"""
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)

def check_database():
    """Check if database is accessible"""
    try:
        import psycopg2
        db_password = os.getenv("DB_PASSWORD", "")
        conn = psycopg2.connect(
            host=DB_HOST,
            port=int(DB_PORT),
            user=DB_USER,
            password=db_password,
            database=DB_NAME,
        )
        conn.close()
        return True
    except Exception as e:
        print(f"✗ Cannot connect to database: {e}")
        return False

def init_schema():
    """Initialize database schema"""
    print_header("INITIALIZING DATABASE SCHEMA")
    print(f"Running: python3 init_database.py")

    result = subprocess.run(
        ["python3", "init_database.py"],
        cwd=Path(__file__).parent,
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        print("✓ Schema initialized")
        return True
    else:
        print("✗ Schema initialization failed")
        print(result.stderr)
        return False

def run_loader(loader, progress):
    """Run a single loader"""
    script = loader["script"]
    name = loader["name"]

    # Check if already completed
    if script in progress["completed"]:
        print(f"⊘ {name}: Already completed ✓")
        return True

    # Check if previously failed
    if script in progress["failed"]:
        print(f"⚠️  {name}: Previously failed")
        if loader["critical"]:
            print(f"   CRITICAL - aborting")
            return False
        else:
            print(f"   Non-critical - skipping")
            return True

    print(f"\n▶ {name}")
    print(f"  Description: {loader['description']}")
    print(f"  Running: python3 {script}")

    start_time = time.time()
    result = subprocess.run(
        ["python3", script],
        cwd=Path(__file__).parent,
        capture_output=True,
        text=True,
        timeout=3600,  # 1 hour timeout per loader
    )
    elapsed = time.time() - start_time

    if result.returncode == 0:
        print(f"  ✓ Completed in {elapsed:.1f}s")
        progress["completed"].append(script)
        save_progress(progress)
        return True
    else:
        print(f"  ✗ Failed after {elapsed:.1f}s")
        print(f"  Error output:")
        for line in result.stderr.split('\n')[-10:]:
            if line.strip():
                print(f"    {line}")
        progress["failed"].append(script)
        save_progress(progress)

        if loader["critical"]:
            print(f"  CRITICAL loader failed - aborting")
            return False
        else:
            print(f"  Non-critical - continuing with next loader")
            return True

def show_summary():
    """Show database summary"""
    try:
        import psycopg2
        db_password = os.getenv("DB_PASSWORD", "")
        conn = psycopg2.connect(
            host=DB_HOST,
            port=int(DB_PORT),
            user=DB_USER,
            password=db_password,
            database=DB_NAME,
        )
        cur = conn.cursor()

        print_header("DATABASE SUMMARY")

        tables = [
            ("stock_symbols", "Symbols loaded"),
            ("price_daily", "Price records"),
            ("company_profile", "Companies"),
            ("key_metrics", "Metrics"),
            ("annual_income_statement", "Annual income statements"),
            ("annual_balance_sheet", "Annual balance sheets"),
            ("annual_cash_flow", "Annual cash flows"),
            ("buy_sell_daily", "Buy/sell signals"),
            ("stock_scores", "Stock scores"),
        ]

        for table, label in tables:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                count = cur.fetchone()[0]
                print(f"  {label:.<40} {count:>10,}")
            except:
                print(f"  {label:.<40} {'N/A':>10}")

        conn.close()
    except Exception as e:
        print(f"Could not generate summary: {e}")

def main():
    """Main entry point"""
    print("\n")
    print("  ╔════════════════════════════════════════════════════════╗")
    print("  ║  AWS Loader Orchestrator - Local Test Mode           ║")
    print("  ║  Tests loaders before pushing to AWS                 ║")
    print("  ╚════════════════════════════════════════════════════════╝")

    # Parse arguments
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-schema", action="store_true", help="Skip schema initialization")
    parser.add_argument("--reset-progress", action="store_true", help="Ignore saved progress and restart")
    parser.add_argument("--loader", help="Run specific loader only")
    parser.add_argument("--critical-only", action="store_true", help="Run only critical loaders")
    args = parser.parse_args()

    # Check database
    print("\nChecking database connection...")
    if not check_database():
        print("✗ Database not accessible - start PostgreSQL first")
        sys.exit(1)
    print("✓ Database is accessible")

    # Initialize schema
    if not args.skip_schema:
        if not init_schema():
            sys.exit(1)

    # Load progress
    progress = load_progress()
    if args.reset_progress:
        progress = {"completed": [], "failed": []}
        print("\n✓ Progress reset")

    # Determine which loaders to run
    loaders_to_run = LOADERS
    if args.critical_only:
        loaders_to_run = [l for l in LOADERS if l["critical"]]
    if args.loader:
        loaders_to_run = [l for l in LOADERS if l["script"] == args.loader]
        if not loaders_to_run:
            print(f"✗ Loader not found: {args.loader}")
            sys.exit(1)

    # Run loaders
    print_header("RUNNING LOADERS")
    print(f"Loaders to run: {len(loaders_to_run)}")
    print(f"Previously completed: {len(progress['completed'])}")
    print(f"Previously failed: {len(progress['failed'])}")

    all_success = True
    for i, loader in enumerate(loaders_to_run, 1):
        print(f"\n[{i}/{len(loaders_to_run)}]", end="")
        if not run_loader(loader, progress):
            all_success = False
            break

        # Rate limiting between loaders
        if i < len(loaders_to_run):
            time.sleep(RATE_LIMIT_SECONDS)

    # Summary
    show_summary()

    # Final status
    print_header("COMPLETION STATUS")
    if all_success:
        print("✓ All loaders completed successfully")
        print("\nNext steps:")
        print("  1. Verify data in database:")
        print(f"     psql -U {DB_USER} -d {DB_NAME}")
        print("  2. Run frontend to verify data loads")
        print("  3. If all good, push to AWS with same loaders")
    else:
        print("✗ Some loaders failed - fix errors and re-run")
        print(f"   Run again: python3 run-loaders.py")
        print(f"   (Progress is saved - will resume from where it stopped)")

    sys.exit(0 if all_success else 1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⊘ Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
