#!/usr/bin/env python3
"""Audit data completeness and report issues"""
import psycopg2
import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger()

def get_connection():
    """Get database connection"""
    try:
        conn = psycopg2.connect(
            host=os.environ.get('DB_HOST', 'localhost'),
            user=os.environ.get('DB_USER', 'stocks'),
            password=os.environ.get('DB_PASSWORD', ''),
            database=os.environ.get('DB_NAME', 'stocks')
        )
        return conn
    except Exception as e:
        logger.error(f"❌ Cannot connect to database: {e}")
        sys.exit(1)

def audit():
    """Run comprehensive data audit"""
    conn = get_connection()
    cur = conn.cursor()

    logger.info("=" * 80)
    logger.info("DATA COMPLETENESS AUDIT")
    logger.info("=" * 80)

    # Get total symbols
    cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE etf IS NULL OR etf != 'Y'")
    total_symbols = cur.fetchone()[0]
    logger.info(f"\n📊 Total symbols to track: {total_symbols}")

    # Check key tables (note: company_profile uses 'ticker' not 'symbol')
    tables = [
        ('company_profile', 'Company profiles', 'ticker'),
        ('positioning_metrics', 'Positioning metrics', 'symbol'),
        ('key_metrics', 'Key metrics', 'ticker'),
        ('buy_sell_daily', 'Buy/Sell signals (Daily)', 'symbol'),
        ('stock_scores', 'Stock scores', 'symbol'),
    ]

    missing_data = {}

    for table_name, display_name, col_name in tables:
        try:
            # Count total records
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            total = cur.fetchone()[0]

            # Count distinct symbols
            cur.execute(f"SELECT COUNT(DISTINCT {col_name}) FROM {table_name}")
            distinct_symbols = cur.fetchone()[0]

            pct = round(distinct_symbols / total_symbols * 100, 1) if total_symbols > 0 else 0

            if distinct_symbols == total_symbols:
                logger.info(f"✅ {display_name}: {distinct_symbols}/{total_symbols} ({pct}%)")
            elif distinct_symbols > total_symbols * 0.9:
                logger.info(f"⚠️  {display_name}: {distinct_symbols}/{total_symbols} ({pct}%) - MOSTLY COMPLETE")
                missing_data[table_name] = total_symbols - distinct_symbols
            else:
                logger.error(f"❌ {display_name}: {distinct_symbols}/{total_symbols} ({pct}%) - SIGNIFICANT DATA LOSS")
                missing_data[table_name] = total_symbols - distinct_symbols

        except Exception as e:
            logger.error(f"❌ {display_name}: Cannot query - {str(e)[:100]}")
            # Rollback transaction on error
            conn.rollback()

    # Check for NULL values in critical columns
    logger.info(f"\n🔍 Checking for NULL values in critical data:")

    nullcheck = [
        ("stock_scores", "symbol", "Symbol"),
        ("stock_scores", "composite_score", "Composite score"),
        ("company_profile", "ticker", "Ticker"),
        ("company_profile", "short_name", "Company name"),
        ("positioning_metrics", "symbol", "Symbol"),
    ]

    for table, col, display in nullcheck:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL")
            null_count = cur.fetchone()[0]
            if null_count == 0:
                logger.info(f"   ✅ {table}.{col}: No NULLs")
            else:
                logger.warning(f"   ⚠️  {table}.{col}: {null_count} NULLs")
        except Exception as e:
            pass

    # Report summary
    logger.info(f"\n{'='*80}")
    if missing_data:
        logger.error(f"\n⚠️  DATA ISSUES FOUND:")
        for table, count in missing_data.items():
            logger.error(f"   - {table}: Missing {count} symbols")
        logger.info(f"\n🔧 ACTION: Run improved loaders to fill gaps:")
        logger.info(f"   python3 loaddailycompanydata.py")
        logger.info(f"   python3 loadbuyselldaily.py")
    else:
        logger.info(f"\n✅ ALL DATA IS COMPLETE!")

    cur.close()
    conn.close()

if __name__ == '__main__':
    audit()
