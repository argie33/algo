#!/usr/bin/env python3
"""
Monitor the complete momentum loading and stock scores rebuild workflow
"""

import psycopg2
import time
import subprocess
import os
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "password"),
        dbname=os.getenv("DB_NAME", "stocks")
    )

def check_momentum_loading_complete():
    """Check if momentum_metrics table has all expected records"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                COUNT(*) as total_records,
                COUNT(DISTINCT symbol) as unique_symbols,
                MAX(date) as latest_date
            FROM momentum_metrics
        """)

        total, unique_syms, latest = cur.fetchone()
        cur.close()
        conn.close()

        logging.info(f"Momentum metrics: {total:,} records, {unique_syms:,} unique symbols, latest: {latest}")

        # Consider complete if we have most symbols (~5000+)
        return unique_syms >= 5000

    except Exception as e:
        logging.warning(f"Could not check momentum status: {e}")
        return False

def run_rebuild_stock_scores():
    """Run rebuild_stock_scores.py"""
    logging.info("=" * 80)
    logging.info("RUNNING STOCK SCORES REBUILD")
    logging.info("=" * 80)

    try:
        result = subprocess.run(
            ["python3", "/home/stocks/algo/rebuild_stock_scores.py"],
            capture_output=True,
            text=True,
            timeout=3600
        )

        logging.info(result.stdout)
        if result.stderr:
            logging.warning(result.stderr)

        return result.returncode == 0

    except subprocess.TimeoutExpired:
        logging.error("Stock scores rebuild timed out!")
        return False
    except Exception as e:
        logging.error(f"Error running stock scores rebuild: {e}")
        return False

def verify_final_results():
    """Verify the final stock scores and check Zillow ranking"""
    logging.info("=" * 80)
    logging.info("VERIFYING FINAL RESULTS")
    logging.info("=" * 80)

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Overall stats
        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN composite_score > 0 THEN 1 END) as with_composite,
                COUNT(CASE WHEN momentum_score > 0 THEN 1 END) as with_momentum,
                ROUND(AVG(composite_score)::NUMERIC, 2) as avg_composite,
                MAX(composite_score) as max_composite,
                MIN(composite_score) as min_composite
            FROM stock_scores
        """)

        stats = cur.fetchone()
        logging.info(f"Total stocks: {stats[0]:,}")
        logging.info(f"With composite score: {stats[1]:,}")
        logging.info(f"With momentum score: {stats[2]:,}")
        logging.info(f"Average composite: {stats[3]}")
        logging.info(f"Max composite: {stats[4]:.2f}")
        logging.info(f"Min composite: {stats[5]:.2f}")

        # Top 10 stocks
        logging.info("\n" + "=" * 80)
        logging.info("TOP 10 STOCKS BY COMPOSITE SCORE")
        logging.info("=" * 80)

        cur.execute("""
            SELECT symbol, composite_score, momentum_score, value_score, quality_score, growth_score
            FROM stock_scores
            WHERE composite_score > 0
            ORDER BY composite_score DESC
            LIMIT 10
        """)

        print(f"\n{'Symbol':<10} {'Composite':<12} {'Momentum':<12} {'Value':<12} {'Quality':<12} {'Growth':<12}")
        print("-" * 70)
        for row in cur.fetchall():
            print(f"{row[0]:<10} {row[1]:<12.2f} {row[2]:<12.2f} {row[3]:<12.2f} {row[4]:<12.2f} {row[5]:<12.2f}")

        # Zillow ranking
        logging.info("\n" + "=" * 80)
        logging.info("ZILLOW (ZG) RANKING")
        logging.info("=" * 80)

        cur.execute("""
            SELECT
                symbol,
                composite_score,
                (SELECT COUNT(*) + 1 FROM stock_scores WHERE composite_score > ss.composite_score) as rank,
                (SELECT COUNT(*) FROM stock_scores) as total_stocks
            FROM stock_scores ss
            WHERE symbol = 'ZG'
        """)

        zg_result = cur.fetchone()
        if zg_result:
            symbol, score, rank, total = zg_result
            logging.info(f"Symbol: {symbol}")
            logging.info(f"Composite Score: {score:.2f}")
            logging.info(f"Rank: #{rank} of {total:,}")
            logging.info(f"Percentile: {(1 - rank/total) * 100:.1f}%")
        else:
            logging.warning("Zillow (ZG) not found in stock_scores table")

        cur.close()
        conn.close()

        return True

    except Exception as e:
        logging.error(f"Error verifying results: {e}")
        return False

def main():
    logging.info("=" * 80)
    logging.info("STOCK SCORING WORKFLOW MONITOR")
    logging.info("=" * 80)

    # Monitor momentum loading
    logging.info("\nMonitoring momentum loading...")
    check_interval = 60  # Check every 60 seconds
    max_wait_time = 14400  # 4 hours max
    elapsed = 0

    while elapsed < max_wait_time:
        if check_momentum_loading_complete():
            logging.info("✅ Momentum loading appears complete!")
            break

        logging.info(f"Momentum still loading... ({elapsed // 60} minutes elapsed)")
        time.sleep(check_interval)
        elapsed += check_interval

    if elapsed >= max_wait_time:
        logging.warning("Reached max wait time for momentum loading")

    # Give it a moment to finalize
    time.sleep(5)

    # Run rebuild
    if run_rebuild_stock_scores():
        # Verify results
        verify_final_results()
        logging.info("\n" + "=" * 80)
        logging.info("✅ WORKFLOW COMPLETE")
        logging.info("=" * 80)
    else:
        logging.error("Stock scores rebuild failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
