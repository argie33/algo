#!/usr/bin/env python3
"""
Diagnostic script to analyze what growth metrics data is available in the database.
Shows exactly why metrics are NULL and what data needs to be populated.
"""

import os
import sys
import psycopg2
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def get_db_connection():
    """Get database connection."""
    try:
        conn = psycopg2.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            port=int(os.environ.get("DB_PORT", "5432")),
            database=os.environ.get("DB_NAME", "stocks"),
            user=os.environ.get("DB_USER", "postgres"),
            password=os.environ.get("DB_PASSWORD", "password"),
        )
        return conn
    except Exception as e:
        logger.error(f"❌ Cannot connect to database: {e}")
        return None


def analyze_symbol(conn, symbol):
    """Analyze what data is available for a specific symbol."""
    try:
        # Create fresh cursor to avoid transaction issues
        cursor = conn.cursor()
    except:
        conn.rollback()
        cursor = conn.cursor()

    logger.info(f"\n{'='*80}")
    logger.info(f"DIAGNOSTIC: {symbol}")
    logger.info(f"{'='*80}")

    try:
        # Check revenue_estimates
        cursor.execute("SELECT COUNT(*) FROM revenue_estimates WHERE symbol = %s;", (symbol,))
        rev_count = cursor.fetchone()[0]
        logger.info(f"✅ revenue_estimates: {rev_count} records" if rev_count > 0 else f"❌ revenue_estimates: 0 records")
    except Exception as e:
        logger.info(f"❌ revenue_estimates: Error - {e}")

    try:
        # Check key_metrics
        cursor.execute(
            "SELECT return_on_equity_pct, revenue_growth_pct, earnings_growth_pct FROM key_metrics WHERE ticker = %s LIMIT 1;",
            (symbol,),
        )
        result = cursor.fetchone()
        if result:
            logger.info(f"✅ key_metrics: ROE={result[0]}, Rev Growth={result[1]}, EPS Growth={result[2]}")
        else:
            logger.info(f"❌ key_metrics: 0 records")
    except Exception as e:
        logger.info(f"❌ key_metrics: Error - {e}")

    # Check quarterly_income_statement
    cursor.execute(
        "SELECT COUNT(*) FROM quarterly_income_statement WHERE symbol = %s;",
        (symbol,),
    )
    qi_count = cursor.fetchone()[0]
    logger.info(f"📊 quarterly_income_statement: {qi_count} total records")

    # Get item_names available
    cursor.execute(
        "SELECT DISTINCT item_name FROM quarterly_income_statement WHERE symbol = %s ORDER BY item_name;",
        (symbol,),
    )
    items = [row[0] for row in cursor.fetchall()]
    if items:
        for item in items:
            cursor.execute(
                "SELECT COUNT(*) FROM quarterly_income_statement WHERE symbol = %s AND item_name = %s;",
                (symbol, item),
            )
            count = cursor.fetchone()[0]
            logger.info(f"   - {item}: {count} quarters")
    else:
        logger.info("   ❌ No item_names found")

    # Check quarterly_cash_flow
    cursor.execute(
        "SELECT COUNT(*) FROM quarterly_cash_flow WHERE symbol = %s;",
        (symbol,),
    )
    qcf_count = cursor.fetchone()[0]
    logger.info(f"💰 quarterly_cash_flow: {qcf_count} total records")

    cursor.execute(
        "SELECT DISTINCT item_name FROM quarterly_cash_flow WHERE symbol = %s ORDER BY item_name;",
        (symbol,),
    )
    items = [row[0] for row in cursor.fetchall()]
    if items:
        for item in items:
            cursor.execute(
                "SELECT COUNT(*) FROM quarterly_cash_flow WHERE symbol = %s AND item_name = %s;",
                (symbol, item),
            )
            count = cursor.fetchone()[0]
            logger.info(f"   - {item}: {count} quarters")
    else:
        logger.info("   ❌ No item_names found")

    # Check quarterly_balance_sheet
    cursor.execute(
        "SELECT COUNT(*) FROM quarterly_balance_sheet WHERE symbol = %s;",
        (symbol,),
    )
    qbs_count = cursor.fetchone()[0]
    logger.info(f"⚖️  quarterly_balance_sheet: {qbs_count} total records")

    cursor.execute(
        "SELECT DISTINCT item_name FROM quarterly_balance_sheet WHERE symbol = %s ORDER BY item_name;",
        (symbol,),
    )
    items = [row[0] for row in cursor.fetchall()]
    if items:
        for item in items[:10]:  # Show first 10
            cursor.execute(
                "SELECT COUNT(*) FROM quarterly_balance_sheet WHERE symbol = %s AND item_name = %s;",
                (symbol, item),
            )
            count = cursor.fetchone()[0]
            logger.info(f"   - {item}: {count} quarters")
        if len(items) > 10:
            logger.info(f"   ... and {len(items) - 10} more item types")
    else:
        logger.info("   ❌ No item_names found")

    cursor.close()


def main():
    """Main execution."""
    conn = get_db_connection()
    if not conn:
        sys.exit(1)

    # Get a sample of symbols to analyze
    cursor = conn.cursor()
    cursor.execute(
        "SELECT symbol FROM stock_symbols WHERE (etf IS NULL OR etf != 'Y') LIMIT 5;"
    )
    symbols = [row[0] for row in cursor.fetchall()]
    cursor.close()

    logger.info(f"Analyzing {len(symbols)} sample symbols...\n")

    for symbol in symbols:
        try:
            analyze_symbol(conn, symbol)
        except Exception as e:
            logger.error(f"Error analyzing {symbol}: {e}")

    conn.close()

    logger.info(f"\n{'='*80}")
    logger.info("SUMMARY: This shows what data is available for growth metrics calculation")
    logger.info("If key_metrics is missing: Need to load from yfinance")
    logger.info("If quarterly_* is missing: Need to load quarterly statements from yfinance")
    logger.info("='*80'")


if __name__ == "__main__":
    main()
