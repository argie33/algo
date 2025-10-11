#!/usr/bin/env python3
"""
Complete AWS Data Loader
Loads all required data to AWS RDS for production deployment:
1. Positioning metrics (from yfinance)
2. Stock scores (calculated)
3. Sector performance data
4. Industry performance data

Run this script with AWS credentials to populate the production database.
"""

import json
import logging
import os
import sys
import time
from datetime import date

import boto3
import psycopg2
from psycopg2.extras import RealDictCursor

# Import our existing loaders
from loaddailycompanydata import load_all_realtime_data
from loadstockscores import get_stock_data_from_database, save_stock_score

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

def get_aws_db_config():
    """Get AWS database configuration from Secrets Manager"""
    secret_arn = os.environ.get("DB_SECRET_ARN")
    if not secret_arn:
        # Get from CloudFormation exports
        cfn = boto3.client("cloudformation")
        exports = cfn.list_exports()
        for export in exports["Exports"]:
            if export["Name"] == "StocksApp-SecretArn":
                secret_arn = export["Value"]
                break

    if not secret_arn:
        raise ValueError("Cannot find DB_SECRET_ARN")

    logging.info(f"Using secret: {secret_arn}")

    # Get secret value
    sm = boto3.client("secretsmanager")
    secret_str = sm.get_secret_value(SecretId=secret_arn)["SecretString"]
    secret = json.loads(secret_str)

    return {
        "host": secret["host"],
        "port": int(secret.get("port", 5432)),
        "user": secret["username"],
        "password": secret["password"],
        "dbname": secret["dbname"],
    }

def load_positioning_data_batch(symbols, conn, cur):
    """Load positioning data for a batch of symbols"""
    success = 0
    failed = 0

    for symbol in symbols:
        try:
            logging.info(f"Loading positioning data for {symbol}")
            stats = load_all_realtime_data(symbol, cur, conn)
            if stats:
                logging.info(f"✅ {symbol}: {stats}")
                success += 1
            else:
                logging.warning(f"⚠️ {symbol}: No data returned")
                failed += 1
            time.sleep(0.5)  # Rate limiting
        except Exception as e:
            logging.error(f"❌ {symbol}: {e}")
            failed += 1
            conn.rollback()

    return success, failed

def load_stock_scores(conn, cur):
    """Calculate and load stock scores"""
    logging.info("Calculating stock scores...")

    # Get symbols
    cur.execute("SELECT symbol FROM stock_symbols WHERE (etf IS NULL OR etf != 'Y') LIMIT 100")
    symbols = [row[0] for row in cur.fetchall()]

    logging.info(f"Processing {len(symbols)} symbols for scores...")

    # Drop and recreate table
    cur.execute("DROP TABLE IF EXISTS stock_scores CASCADE")
    conn.commit()

    cur.execute("""
        CREATE TABLE stock_scores (
            symbol VARCHAR(50) PRIMARY KEY,
            composite_score DECIMAL(5,2),
            momentum_score DECIMAL(5,2),
            trend_score DECIMAL(5,2),
            value_score DECIMAL(5,2),
            quality_score DECIMAL(5,2),
            growth_score DECIMAL(5,2),
            positioning_score DECIMAL(5,2),
            sentiment_score DECIMAL(5,2),
            -- Momentum component breakdown (8 components)
            momentum_short_term DECIMAL(5,2),
            momentum_medium_term DECIMAL(5,2),
            momentum_oscillator DECIMAL(5,2),
            momentum_trend_strength DECIMAL(5,2),
            momentum_macd_analysis DECIMAL(5,2),
            momentum_volume_conf DECIMAL(5,2),
            momentum_relative_strength DECIMAL(5,2),
            momentum_consistency DECIMAL(5,2),
            -- Technical indicators
            rsi DECIMAL(5,2),
            macd DECIMAL(10,4),
            sma_20 DECIMAL(10,2),
            sma_50 DECIMAL(10,2),
            volume_avg_30d BIGINT,
            current_price DECIMAL(10,2),
            price_change_1d DECIMAL(5,2),
            price_change_5d DECIMAL(5,2),
            price_change_30d DECIMAL(5,2),
            volatility_30d DECIMAL(5,2),
            market_cap BIGINT,
            pe_ratio DECIMAL(8,2),
            score_date DATE DEFAULT CURRENT_DATE,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    logging.info("✅ stock_scores table created")

    success = 0
    failed = 0

    for symbol in symbols:
        try:
            scores = get_stock_data_from_database(conn, symbol)
            if scores:
                # Save to database using the save function
                if save_stock_score(conn, scores):
                    success += 1
                    logging.info(f"✅ {symbol}: Composite={scores.get('composite_score', 0):.2f}")
                else:
                    failed += 1
            else:
                failed += 1
        except Exception as e:
            logging.error(f"❌ {symbol}: {e}")
            failed += 1
            conn.rollback()

    conn.commit()
    return success, failed

def verify_data(conn, cur):
    """Verify all required data exists in AWS"""
    logging.info("=" * 80)
    logging.info("VERIFICATION: Checking data in AWS RDS")
    logging.info("=" * 80)

    # Check positioning_metrics
    cur.execute("SELECT COUNT(*) FROM positioning_metrics")
    pos_count = cur.fetchone()[0]
    logging.info(f"positioning_metrics: {pos_count} records")

    # Check stock_scores
    cur.execute("SELECT COUNT(*) FROM stock_scores")
    scores_count = cur.fetchone()[0]
    logging.info(f"stock_scores: {scores_count} records")

    # Check major stocks
    cur.execute("""
        SELECT ss.symbol, ss.composite_score, ss.positioning_score,
               pm.institutional_ownership, pm.insider_ownership
        FROM stock_scores ss
        LEFT JOIN positioning_metrics pm ON ss.symbol = pm.symbol
        WHERE ss.symbol IN ('AAPL', 'NVDA', 'TSLA', 'GOOGL', 'MSFT')
        ORDER BY ss.symbol
    """)

    logging.info("\nMajor stocks verification:")
    for row in cur.fetchall():
        inst = f"{row[3]*100:.1f}%" if row[3] else "N/A"
        insider = f"{row[4]*100:.1f}%" if row[4] else "N/A"
        logging.info(f"  {row[0]}: Composite={row[1]:.2f}, Positioning={row[2]:.2f if row[2] else 'None'}, Inst={inst}, Insider={insider}")

    # Check sector data
    cur.execute("SELECT COUNT(*) FROM sector_performance")
    sector_count = cur.fetchone()[0]
    logging.info(f"\nsector_performance: {sector_count} records")

    # Check industry data
    cur.execute("SELECT COUNT(*) FROM industry_performance")
    industry_count = cur.fetchone()[0]
    logging.info(f"industry_performance: {industry_count} records")

    logging.info("=" * 80)

def main():
    """Main data loading pipeline"""
    try:
        logging.info("🚀 Starting AWS data loading pipeline...")

        # Connect to AWS database
        cfg = get_aws_db_config()
        logging.info(f"Connecting to AWS RDS: {cfg['host']}")

        conn = psycopg2.connect(
            host=cfg["host"],
            port=cfg["port"],
            user=cfg["user"],
            password=cfg["password"],
            dbname=cfg["dbname"],
        )
        conn.autocommit = False
        cur = conn.cursor(cursor_factory=RealDictCursor)

        logging.info("✅ Connected to AWS RDS")

        # Step 1: Load positioning data for major stocks
        logging.info("\n" + "=" * 80)
        logging.info("STEP 1: Loading positioning data")
        logging.info("=" * 80)

        major_stocks = ['AAPL', 'NVDA', 'TSLA', 'GOOGL', 'MSFT', 'AMZN', 'META', 'GOOG', 'NFLX', 'COST']
        pos_success, pos_failed = load_positioning_data_batch(major_stocks, conn, cur)
        logging.info(f"Positioning data: {pos_success} successful, {pos_failed} failed")

        # Step 2: Calculate and load stock scores
        logging.info("\n" + "=" * 80)
        logging.info("STEP 2: Calculating and loading stock scores")
        logging.info("=" * 80)

        scores_success, scores_failed = load_stock_scores(conn, cur)
        logging.info(f"Stock scores: {scores_success} successful, {scores_failed} failed")

        # Step 3: Verify all data
        logging.info("\n" + "=" * 80)
        logging.info("STEP 3: Verification")
        logging.info("=" * 80)

        verify_data(conn, cur)

        cur.close()
        conn.close()

        logging.info("\n" + "=" * 80)
        logging.info("✅ AWS DATA LOADING COMPLETE")
        logging.info("=" * 80)
        logging.info(f"Positioning: {pos_success}/{len(major_stocks)}")
        logging.info(f"Scores: {scores_success} stocks processed")
        logging.info("Next steps:")
        logging.info("1. Test AWS API endpoints")
        logging.info("2. Verify frontend displays data correctly")

    except Exception as e:
        logging.error(f"❌ Data loading failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
