#!/usr/bin/env python3
"""Comprehensive production system verification script."""
import os
import sys
import logging
import psycopg2
from datetime import datetime, date

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def check_db_connectivity():
    """Test RDS connection."""
    logger.info("\n=== DATABASE CONNECTIVITY ===")
    try:
        host, user, password, db_name = os.getenv('DB_HOST'), os.getenv('DB_USER'), os.getenv('DB_PASSWORD'), os.getenv('DB_NAME')
        if not all([host, user, password, db_name]):
            logger.error("Missing database credentials")
            return False
        conn = psycopg2.connect(host=host, user=user, password=password, database=db_name)
        cur = conn.cursor()
        cur.execute("SELECT version();")
        logger.info(f"✓ Connected: {cur.fetchone()[0][:50]}...")
        cur.close()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"✗ Connection failed: {e}")
        return False

def check_schema():
    """Verify required tables exist."""
    logger.info("\n=== SCHEMA COMPLETENESS ===")
    required_tables = [
        'price_daily', 'technical_data_daily', 'buy_sell_daily', 'stock_scores',
        'algo_component_attribution', 'algo_weight_history', 'earnings_metrics',
        'algo_positions', 'algo_audit_log', 'data_loader_status', 'data_patrol_log'
    ]
    try:
        conn = psycopg2.connect(host=os.getenv('DB_HOST'), user=os.getenv('DB_USER'), password=os.getenv('DB_PASSWORD'), database=os.getenv('DB_NAME'))
        cur = conn.cursor()
        missing = []
        for table in required_tables:
            try:
                cur.execute(f"SELECT 1 FROM {table} LIMIT 1;")
                logger.info(f"✓ {table}")
            except:
                missing.append(table)
                logger.warning(f"✗ {table}")
        cur.close()
        conn.close()
        if missing:
            logger.error(f"Missing: {missing}")
            return False
        logger.info(f"✓ All {len(required_tables)} tables exist")
        return True
    except Exception as e:
        logger.error(f"Schema check failed: {e}")
        return False

def main():
    logger.info("="*60)
    logger.info("PRODUCTION SYSTEM VERIFICATION")
    logger.info(f"Started: {datetime.now()}")
    logger.info("="*60)
    results = {'connectivity': check_db_connectivity(), 'schema': check_schema()}
    logger.info("\n" + "="*60)
    for check, passed in results.items():
        logger.info(f"{'✓' if passed else '✗'}: {check.replace('_', ' ').title()}")
    logger.info("="*60)
    return 0 if all(results.values()) else 1

if __name__ == '__main__':
    sys.exit(main())
