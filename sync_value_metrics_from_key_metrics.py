#!/usr/bin/env python3
"""
Sync VALUE METRICS from KEY_METRICS

The key_metrics table has trailing_pe, forward_pe, price_to_sales_ttm, price_to_book, etc.
We need to copy these INTO value_metrics table so the data is complete.

This script does:
1. For each symbol in key_metrics with P/E data
2. Copy/update the value_metrics table with those real values
3. No calculations needed - just copy from key_metrics to value_metrics
"""
import psycopg2
import psycopg2.extras
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

conn = psycopg2.connect(host="localhost", database="stocks", user="stocks", password="")
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

logging.info("=" * 80)
logging.info("SYNCING VALUE METRICS FROM KEY_METRICS")
logging.info("=" * 80)

# Get all symbols that have key_metrics with P/E data
cur.execute("""
    SELECT
        ticker as symbol,
        trailing_pe,
        forward_pe,
        price_to_sales_ttm,
        price_to_book,
        peg_ratio,
        ev_to_revenue,
        ev_to_ebitda,
        dividend_yield,
        payout_ratio
    FROM key_metrics
    WHERE trailing_pe IS NOT NULL OR price_to_sales_ttm IS NOT NULL
    ORDER BY ticker
""")

rows = cur.fetchall()
logging.info(f"Found {len(rows)} symbols with value data in key_metrics")

updated = 0

for row in rows:
    try:
        symbol = row['symbol']

        # Build UPDATE statement with all value metrics from key_metrics
        cur.execute("""
            UPDATE value_metrics SET
                trailing_pe = %s,
                forward_pe = %s,
                price_to_sales_ttm = %s,
                price_to_book = %s,
                peg_ratio = %s,
                ev_to_revenue = %s,
                ev_to_ebitda = %s,
                dividend_yield = %s,
                payout_ratio = %s,
                created_at = NOW()
            WHERE symbol = %s
        """, (
            row['trailing_pe'],
            row['forward_pe'],
            row['price_to_sales_ttm'],
            row['price_to_book'],
            row['peg_ratio'],
            row['ev_to_revenue'],
            row['ev_to_ebitda'],
            row['dividend_yield'],
            row['payout_ratio'],
            symbol
        ))

        if cur.rowcount > 0:
            conn.commit()
            updated += 1
            if updated % 100 == 0:
                logging.info(f"Updated {updated} symbols...")
        else:
            logging.warning(f"No row updated for {symbol} - value_metrics entry may not exist")

    except Exception as e:
        conn.rollback()
        logging.error(f"Error for {row.get('symbol')}: {str(e)[:100]}")
        continue

logging.info("=" * 80)
logging.info(f"✅ SYNC COMPLETE: {updated} value_metrics updated from key_metrics")
logging.info("=" * 80)

# Verify coverage
cur.execute("""
    SELECT
        COUNT(*) as total,
        COUNT(CASE WHEN trailing_pe IS NOT NULL THEN 1 END) as with_pe,
        COUNT(CASE WHEN price_to_sales_ttm IS NOT NULL THEN 1 END) as with_ps,
        ROUND(100.0 * COUNT(CASE WHEN trailing_pe IS NOT NULL THEN 1 END) / COUNT(*), 1) as pct_pe
    FROM value_metrics
""")

final = cur.fetchone()
logging.info(f"Final coverage: {final['with_pe']}/{final['total']} ({final['pct_pe']}%) with P/E")

conn.close()
