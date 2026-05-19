#!/usr/bin/env python3
"""
Run a complete test cycle: load data, generate signals, run orchestrator.

Usage:
  python3 run_test_cycle.py
"""

import subprocess
import sys
from datetime import date
from utils.db_connection import get_db_connection


def run_cmd(label: str, cmd: str) -> bool:
    """Run a loader command, return True if successful."""
    print(f"\n{'='*70}")
    print(f"[{label}]")
    print(f"{'='*70}")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=False, text=True)
        if result.returncode == 0:
            print(f"✓ {label} completed successfully")
            return True
        else:
            print(f"✗ {label} failed (exit code {result.returncode})")
            return False
    except Exception as e:
        print(f"✗ {label} error: {e}")
        return False


def check_data(label: str, table: str, min_count: int = 1) -> bool:
    """Check if data was loaded for today."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE date = CURRENT_DATE")
        count = cur.fetchone()[0]
        conn.close()

        status = "✓" if count >= min_count else "✗"
        print(f"{status} {label}: {count:,} records")
        return count >= min_count
    except Exception as e:
        print(f"✗ {label} error: {e}")
        return False


def main():
    """Run test cycle."""
    today = date.today()
    print(f"\nSWING TRADING TEST CYCLE — {today}")
    print("=" * 70)

    # Step 1: Load prices
    success = run_cmd(
        "STEP 1: Load Prices",
        "python3 loaders/loadpricedaily.py --interval 1d --asset-class stock"
    )
    if not success:
        print("\n[FATAL] Price loader failed. Stopping.")
        return False

    check_data("Prices for today", "price_daily", min_count=4000)

    # Step 2: Load technicals
    success = run_cmd(
        "STEP 2: Load Technical Indicators",
        "python3 loaders/load_technical_data_daily.py"
    )
    check_data("Technicals", "technical_data_daily", min_count=4000)

    # Step 3: Load market health
    success = run_cmd(
        "STEP 3: Load Market Health",
        "python3 loaders/load_market_health_daily.py"
    )
    check_data("Market health", "market_health_daily", min_count=1)

    # Step 4: Load trend template
    success = run_cmd(
        "STEP 4: Load Trend Template",
        "python3 loaders/load_trend_criteria_data.py"
    )
    check_data("Trend criteria", "trend_criteria", min_count=4000)

    # Step 5: Load stock scores
    success = run_cmd(
        "STEP 5: Load Stock Scores",
        "python3 loaders/loadstockscores.py"
    )
    check_data("Stock scores", "stock_scores", min_count=4000)

    # Step 6: Generate signals
    success = run_cmd(
        "STEP 6: Generate Buy/Sell Signals",
        "python3 loaders/loadbuyselldaily.py"
    )
    check_data("Buy/sell signals", "buy_sell_daily", min_count=50)

    # Step 7: Load swing trader scores
    success = run_cmd(
        "STEP 7: Load Swing Trader Scores",
        "python3 loaders/load_swing_trader_scores.py"
    )
    check_data("Swing trader scores", "swing_trader_scores", min_count=4000)

    # Step 8: Run orchestrator (dry-run)
    success = run_cmd(
        "STEP 8: Run Orchestrator (DRY-RUN)",
        "python3 algo/algo_orchestrator.py --dry-run"
    )

    # Summary
    print(f"\n\n{'='*70}")
    print("TEST CYCLE COMPLETE")
    print(f"{'='*70}")

    # Check final state
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            (SELECT COUNT(*) FROM price_daily WHERE date = CURRENT_DATE) as prices,
            (SELECT COUNT(*) FROM technical_data_daily WHERE date = CURRENT_DATE) as technicals,
            (SELECT COUNT(*) FROM buy_sell_daily WHERE date = CURRENT_DATE) as signals,
            (SELECT COUNT(*) FROM swing_trader_scores WHERE date = CURRENT_DATE) as scores
    """)

    prices, technicals, signals, scores = cur.fetchone()

    print(f"\nData Loaded for {today}:")
    print(f"  Prices:          {prices:,}")
    print(f"  Technicals:      {technicals:,}")
    print(f"  Signals:         {signals:,}")
    print(f"  Swing Scores:    {scores:,}")

    # Check if data is complete enough
    all_good = all([
        prices >= 4000,
        technicals >= 4000,
        signals >= 50,
        scores >= 4000
    ])

    if all_good:
        print("\n✓ ALL DATA LOADED SUCCESSFULLY")
        print("\nYou can now:")
        print("  1. Run live orchestrator: ORCHESTRATOR_DRY_RUN=false python3 algo/algo_orchestrator.py")
        print("  2. Deploy to AWS: cd terraform && terraform apply")
        print("  3. Monitor schedules: aws events list-rules --region us-east-1")
    else:
        print("\n✗ Some data incomplete. Check logs above for errors.")
        print("\nTroubleshooting:")
        if prices < 4000:
            print("  - Price loader: check yfinance API, network, rate limits")
        if technicals < 4000:
            print("  - Technical loader: check price_daily exists first")
        if signals < 50:
            print("  - Signal loader: check technical_data_daily populated")
        if scores < 4000:
            print("  - Score loader: check if dependencies ready")

    conn.close()
    return all_good


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
