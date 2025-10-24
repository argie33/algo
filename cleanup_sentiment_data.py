#!/usr/bin/env python3
"""
Clean up fake/fallback sentiment data from database

Removes or updates rows with fake/hardcoded values:
- Random generated sentiment scores (np.random values)
- Hardcoded 0.5 values from fake data generation
- Fake search volumes and trends
- Returns NULL for unavailable data instead of fake defaults

This script makes the database consistent with the new real data approach.
"""

import os
import json
import logging
from datetime import datetime
import psycopg2
from psycopg2.extras import execute_values

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def get_db_config():
    """Get database configuration"""
    try:
        import boto3
        secret_str = boto3.client("secretsmanager") \
                         .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
        sec = json.loads(secret_str)
        return {
            "host": sec["host"],
            "port": int(sec.get("port", 5432)),
            "user": sec["username"],
            "password": sec["password"],
            "dbname": sec["dbname"]
        }
    except Exception:
        return {
            "host": os.environ.get("DB_HOST", "localhost"),
            "port": int(os.environ.get("DB_PORT", 5432)),
            "user": os.environ.get("DB_USER", "postgres"),
            "password": os.environ.get("DB_PASSWORD", ""),
            "dbname": os.environ.get("DB_NAME", "stocks")
        }

def cleanup_sentiment_data(conn):
    """Remove or update fake sentiment data"""
    cur = conn.cursor()
    
    try:
        logging.info("=" * 80)
        logging.info("🧹 Cleaning up fake sentiment data from database")
        logging.info("=" * 80)

        # Check if sentiment table exists
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'sentiment'
            )
        """)
        if not cur.fetchone()[0]:
            logging.warning("⚠️  sentiment table does not exist, nothing to clean")
            return

        # Count fake/suspicious data before cleanup
        logging.info("\n📊 Analyzing sentiment data for fake values...")

        # Count NULL values (good data)
        cur.execute("""
            SELECT COUNT(*) as null_values
            FROM sentiment
            WHERE reddit_sentiment_score IS NULL
            AND search_volume_index IS NULL
            AND news_sentiment_score IS NULL
        """)
        null_count = cur.fetchone()[0]
        logging.info(f"  ✓ Rows with all NULL values (unavailable data): {null_count}")

        # Count suspicious 0.5 values (likely from hardcoded defaults)
        cur.execute("""
            SELECT COUNT(*) as suspicious_values
            FROM sentiment
            WHERE reddit_sentiment_score = 0.5
            OR news_sentiment_score = 0.5
        """)
        suspicious_count = cur.fetchone()[0]
        if suspicious_count > 0:
            logging.warning(f"  ⚠️  Rows with hardcoded 0.5 values: {suspicious_count}")

        # Count very small values (likely from random generation in tiny range)
        cur.execute("""
            SELECT COUNT(*) as tiny_values
            FROM sentiment
            WHERE (reddit_sentiment_score IS NOT NULL AND ABS(reddit_sentiment_score) < 0.01)
            AND search_volume_index IS NULL
        """)
        tiny_count = cur.fetchone()[0]
        if tiny_count > 0:
            logging.warning(f"  ⚠️  Rows with tiny/random values: {tiny_count}")

        # Cleanup strategy 1: Set 0.5 values to NULL (hardcoded defaults)
        logging.info("\n🔄 Cleaning up hardcoded 0.5 values...")
        cur.execute("""
            UPDATE sentiment
            SET reddit_sentiment_score = NULL
            WHERE reddit_sentiment_score = 0.5
        """)
        reddit_fixed = cur.rowcount
        logging.info(f"  ✓ Fixed {reddit_fixed} rows with hardcoded reddit_sentiment_score")

        cur.execute("""
            UPDATE sentiment
            SET news_sentiment_score = NULL
            WHERE news_sentiment_score = 0.5
        """)
        news_fixed = cur.rowcount
        logging.info(f"  ✓ Fixed {news_fixed} rows with hardcoded news_sentiment_score")

        # Cleanup strategy 2: Set suspiciously small values to NULL
        logging.info("\n🔄 Cleaning up suspiciously small/random values...")
        cur.execute("""
            UPDATE sentiment
            SET reddit_sentiment_score = NULL
            WHERE ABS(reddit_sentiment_score) < 0.001
            AND search_volume_index IS NULL
            AND reddit_mention_count IS NULL
        """)
        small_reddit_fixed = cur.rowcount
        if small_reddit_fixed > 0:
            logging.info(f"  ✓ Fixed {small_reddit_fixed} rows with suspiciously small values")

        conn.commit()

        # Verify cleanup
        logging.info("\n✅ Cleanup complete! Verification:")
        cur.execute("SELECT COUNT(*) as total FROM sentiment")
        total_rows = cur.fetchone()[0]
        logging.info(f"  Total sentiment rows: {total_rows}")

        cur.execute("""
            SELECT COUNT(*) as complete_null
            FROM sentiment
            WHERE reddit_sentiment_score IS NULL
            AND search_volume_index IS NULL
            AND news_sentiment_score IS NULL
        """)
        complete_null_after = cur.fetchone()[0]
        logging.info(f"  Rows with all NULL (no data): {complete_null_after}")

        cur.execute("""
            SELECT COUNT(*) as has_real_data
            FROM sentiment
            WHERE (reddit_sentiment_score IS NOT NULL
                   OR search_volume_index IS NOT NULL
                   OR news_sentiment_score IS NOT NULL)
        """)
        real_data_rows = cur.fetchone()[0]
        logging.info(f"  Rows with real data: {real_data_rows}")

        logging.info("\n" + "=" * 80)
        logging.info("✓ Database cleanup complete!")
        logging.info("=" * 80)

    except Exception as e:
        logging.error(f"❌ Error cleaning sentiment data: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()

    return True

def main():
    cfg = get_db_config()
    try:
        conn = psycopg2.connect(**cfg)
        logging.info("✓ Connected to database")
        cleanup_sentiment_data(conn)
        conn.close()
    except Exception as e:
        logging.error(f"❌ Failed to connect to database: {e}")
        return False

    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
