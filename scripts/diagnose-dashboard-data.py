#!/usr/bin/env python3
"""Diagnose dashboard data availability - check what tables exist and have data."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
import os
import psycopg2
from datetime import date

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def get_db_connection():
    """Create database connection from environment variables."""
    return psycopg2.connect(
        host=os.getenv('DB_HOST'),
        port=int(os.getenv('DB_PORT', 5432)),
        database=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD')
    )

# Key tables the dashboard queries
CRITICAL_TABLES = {
    'algo_portfolio_snapshots': 'Portfolio snapshots (equity curve)',
    'algo_positions_with_risk': 'Positions with risk metrics',
    'algo_trades': 'Trade history',
    'algo_performance_daily': 'Performance metrics (hourly)',
    'algo_performance_metrics': 'Performance metrics (nightly)',
    'circuit_breaker_status': 'Circuit breaker status',
    'market_health_daily': 'Market health data',
    'buy_sell_daily': 'Buy/sell signals',
    'signal_quality_scores': 'Signal quality scores',
    'algo_positions': 'Algo positions (base)',
}

def check_table_exists(conn, table_name):
    """Check if table exists and return row count + max date."""
    try:
        # Use a fresh cursor for each check to avoid transaction state issues
        cur = conn.cursor()

        # Check if table or materialized view exists
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = %s
            ) OR EXISTS (
                SELECT FROM pg_matviews
                WHERE schemaname = 'public'
                AND matviewname = %s
            )
        """, (table_name, table_name))
        exists = cur.fetchone()[0]
        cur.close()

        if not exists:
            return {'exists': False, 'row_count': 0, 'latest_date': None}

        # Get row count with fresh cursor
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        row_count = cur.fetchone()[0]
        cur.close()

        # Try to find latest date (look for common date columns)
        latest_date = None
        for date_col in ['date', 'snapshot_date', 'report_date', 'metric_date', 'check_date', 'created_at']:
            try:
                cur = conn.cursor()
                cur.execute(f"SELECT MAX({date_col}) FROM {table_name}")
                latest_date = cur.fetchone()[0]
                cur.close()
                if latest_date:
                    break
            except:
                try:
                    cur.close()
                except:
                    pass

        return {'exists': True, 'row_count': row_count, 'latest_date': latest_date}
    except Exception as e:
        try:
            cur.close()
        except:
            pass
        return {'exists': False, 'error': str(e)}

def main():
    try:
        conn = get_db_connection()
        # Use autocommit mode for diagnostic queries to avoid transaction abort issues
        conn.autocommit = True
        logger.info("✓ Database connection successful\n")

        logger.info("=" * 70)
        logger.info("DASHBOARD DATA AVAILABILITY CHECK")
        logger.info("=" * 70 + "\n")

        # Check each critical table
        missing_tables = []
        empty_tables = []
        healthy_tables = []

        for table_name, description in CRITICAL_TABLES.items():
            status = check_table_exists(conn, table_name)

            if not status['exists']:
                missing_tables.append((table_name, description))
                logger.info(f"❌ {table_name:<40} MISSING")
                if 'error' in status:
                    logger.info(f"   Error: {status['error']}")
            elif status['row_count'] == 0:
                empty_tables.append((table_name, description))
                logger.info(f"⚠️  {table_name:<40} EMPTY ({status['row_count']} rows)")
            else:
                healthy_tables.append((table_name, description, status['row_count'], status['latest_date']))
                logger.info(f"✓  {table_name:<40} OK ({status['row_count']} rows, latest: {status['latest_date']})")

        logger.info("\n" + "=" * 70)
        logger.info("SUMMARY")
        logger.info("=" * 70)
        logger.info(f"Healthy tables:    {len(healthy_tables)}")
        logger.info(f"Empty tables:      {len(empty_tables)}")
        logger.info(f"Missing tables:    {len(missing_tables)}")

        if missing_tables:
            logger.info("\nMISSING TABLES (must be created by migrations):")
            for name, desc in missing_tables:
                logger.info(f"  - {name}: {desc}")

        if empty_tables:
            logger.info("\nEMPTY TABLES (loaders haven't run yet):")
            for name, desc in empty_tables:
                logger.info(f"  - {name}: {desc}")

        if healthy_tables:
            logger.info("\nHEALTHY TABLES (dashboard should work):")
            for name, desc, count, latest in healthy_tables:
                logger.info(f"  - {name}: {count} rows, latest={latest}")

        # Check which loaders might need to run
        if empty_tables or missing_tables:
            logger.info("\nRECOMMENDATIONS:")
            if 'algo_performance_daily' in [t[0] for t in empty_tables]:
                logger.info("  1. Run: python loaders/load_algo_performance_daily.py")
            if 'circuit_breaker_status' in [t[0] for t in empty_tables]:
                logger.info("  2. Run: python loaders/compute_circuit_breakers.py")
            if 'algo_positions_with_risk' in [t[0] for t in missing_tables]:
                logger.info("  3. Missing view - check migrations in /migrations")
            if 'buy_sell_daily' in [t[0] for t in empty_tables]:
                logger.info("  4. Run: python loaders/load_buy_sell_daily.py")

        conn.close()

    except Exception as e:
        logger.error(f"✗ Database connection failed: {e}")
        logger.error(f"\nChecklist:")
        logger.error(f"  - DB_HOST: {os.getenv('DB_HOST', 'NOT SET')}")
        logger.error(f"  - DB_NAME: {os.getenv('DB_NAME', 'NOT SET')}")
        logger.error(f"  - DB_USER: {os.getenv('DB_USER', 'NOT SET')}")
        logger.error(f"  - DB_PASSWORD: {'SET' if os.getenv('DB_PASSWORD') else 'NOT SET'}")
        sys.exit(1)

if __name__ == '__main__':
    main()
