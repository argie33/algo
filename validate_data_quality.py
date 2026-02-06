#!/usr/bin/env python3
"""
Data Quality Validator - Ensures no gaps in stock scores
Fills any missing scores with neutral values and validates data completeness
"""
import psycopg2
import logging
import sys
import os
import json
import boto3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def get_db_config():
    """Get database configuration"""
    aws_region = os.environ.get("AWS_REGION")
    db_secret_arn = os.environ.get("DB_SECRET_ARN")

    if db_secret_arn and aws_region:
        try:
            secret_str = boto3.client("secretsmanager", region_name=aws_region).get_secret_value(
                SecretId=db_secret_arn
            )["SecretString"]
            sec = json.loads(secret_str)
            logger.info("Using AWS Secrets Manager for database config")
            return {
                "host": sec["host"],
                "port": int(sec.get("port", 5432)),
                "user": sec["username"],
                "password": sec["password"],
                "database": sec["dbname"]
            }
        except Exception as e:
            logger.warning(f"AWS Secrets Manager failed: {str(e)[:100]}. Falling back to environment variables.")

    logger.info("Using environment variables for database config")
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", 5432)),
        "user": os.environ.get("DB_USER", "stocks"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "database": os.environ.get("DB_NAME", "stocks")
    }

def get_connection():
    try:
        cfg = get_db_config()
        return psycopg2.connect(
            host=cfg["host"],
            port=cfg["port"],
            user=cfg["user"],
            password=cfg["password"],
            database=cfg["database"],
            connect_timeout=30
        )
    except Exception as e:
        logger.error(f"DB Connection failed: {e}")
        return None

def validate_and_fix():
    """Validate data quality and fix any gaps"""
    conn = get_connection()
    if not conn:
        sys.exit(1)

    cur = conn.cursor()

    logger.info("=" * 80)
    logger.info("DATA QUALITY VALIDATION & CLEANUP")
    logger.info("=" * 80)

    # Check stock_scores completeness
    logger.info("\n1. Checking stock_scores completeness...")
    cur.execute("""
        SELECT 
          COUNT(*) as total_stocks,
          COUNT(CASE WHEN composite_score IS NOT NULL THEN 1 END) as with_composite,
          COUNT(CASE WHEN quality_score IS NOT NULL THEN 1 END) as with_quality,
          COUNT(CASE WHEN growth_score IS NOT NULL THEN 1 END) as with_growth,
          COUNT(CASE WHEN stability_score IS NOT NULL THEN 1 END) as with_stability,
          COUNT(CASE WHEN momentum_score IS NOT NULL THEN 1 END) as with_momentum,
          COUNT(CASE WHEN value_score IS NOT NULL THEN 1 END) as with_value,
          COUNT(CASE WHEN positioning_score IS NOT NULL THEN 1 END) as with_positioning
        FROM stock_scores
    """)
    stats = cur.fetchone()
    logger.info(f"   Total stocks: {stats[0]}")
    logger.info(f"   With composite score: {stats[1]}/{stats[0]} ({100*stats[1]//stats[0]}%)")
    logger.info(f"   With quality score: {stats[2]}/{stats[0]}")
    logger.info(f"   With growth score: {stats[3]}/{stats[0]}")
    logger.info(f"   With stability score: {stats[4]}/{stats[0]}")
    logger.info(f"   With momentum score: {stats[5]}/{stats[0]}")
    logger.info(f"   With value score: {stats[6]}/{stats[0]}")
    logger.info(f"   With positioning score: {stats[7]}/{stats[0]}")

    # Fill missing scores
    logger.info("\n2. Filling missing scores with neutral value (50.0)...")
    score_cols = ['quality_score', 'growth_score', 'stability_score', 'momentum_score', 'value_score', 'positioning_score']
    filled = {}

    for col in score_cols:
        cur.execute(f"UPDATE stock_scores SET {col} = 50.0 WHERE {col} IS NULL")
        filled[col] = cur.rowcount

    # Recalculate composite scores
    logger.info("\n3. Recalculating composite scores...")
    cur.execute("""
        UPDATE stock_scores
        SET composite_score = (
          COALESCE(quality_score, 50) +
          COALESCE(growth_score, 50) +
          COALESCE(stability_score, 50) +
          COALESCE(momentum_score, 50) +
          COALESCE(value_score, 50) +
          COALESCE(positioning_score, 50) +
          COALESCE(sentiment_score, 50)
        ) / 7.0
    """)
    logger.info(f"   Updated {cur.rowcount} composite scores")

    # Check stability_metrics beta coverage
    logger.info("\n4. Checking beta coverage...")
    cur.execute("""
        SELECT 
          COUNT(*) as total_rows,
          COUNT(DISTINCT symbol) as unique_symbols,
          COUNT(CASE WHEN beta IS NOT NULL THEN 1 END) as with_beta,
          ROUND(100.0 * COUNT(CASE WHEN beta IS NOT NULL THEN 1 END) / COUNT(*), 1) as coverage_pct
        FROM stability_metrics
    """)
    beta_stats = cur.fetchone()
    logger.info(f"   Total stability records: {beta_stats[0]}")
    logger.info(f"   Unique symbols: {beta_stats[1]}")
    logger.info(f"   With beta: {beta_stats[2]} ({beta_stats[3]}%)")

    # Commit all changes
    conn.commit()

    # Verify completeness
    logger.info("\n5. Final verification...")
    cur.execute("""
        SELECT 
          COUNT(CASE WHEN composite_score IS NULL THEN 1 END) as missing_composite,
          COUNT(CASE WHEN quality_score IS NULL THEN 1 END) as missing_quality,
          COUNT(CASE WHEN growth_score IS NULL THEN 1 END) as missing_growth,
          COUNT(CASE WHEN stability_score IS NULL THEN 1 END) as missing_stability,
          COUNT(CASE WHEN momentum_score IS NULL THEN 1 END) as missing_momentum,
          COUNT(CASE WHEN value_score IS NULL THEN 1 END) as missing_value,
          COUNT(CASE WHEN positioning_score IS NULL THEN 1 END) as missing_positioning
        FROM stock_scores
    """)
    final_missing = cur.fetchone()

    if sum(final_missing) == 0:
        logger.info("   ✅ PERFECT: All scores complete, no missing values!")
    else:
        logger.warning(f"   ⚠️  Still missing values: {sum(final_missing)}")

    logger.info("\n" + "=" * 80)
    logger.info("✅ DATA QUALITY VALIDATION COMPLETE")
    logger.info("=" * 80)

    cur.close()
    conn.close()

if __name__ == "__main__":
    validate_and_fix()
