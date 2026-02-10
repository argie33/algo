#!/usr/bin/env python3
"""
Sync ALL VALUE METRICS from KEY_METRICS - including partial data

The problem: We only synced records with trailing_pe, but many symbols have
forward_pe, price_to_sales_ttm, price_to_book, etc. even if trailing_pe is NULL

This script syncs ALL available value data from key_metrics to value_metrics,
not just trailing_pe.
"""
import psycopg2
import psycopg2.extras
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

conn = psycopg2.connect(host="localhost", database="stocks", user="stocks", password="")
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

logging.info("=" * 80)
logging.info("SYNC ALL VALUE METRICS (including partial data)")
logging.info("=" * 80)

# Get ALL key_metrics regardless of whether they have trailing_pe or not
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
    WHERE trailing_pe IS NOT NULL
       OR forward_pe IS NOT NULL
       OR price_to_sales_ttm IS NOT NULL
       OR price_to_book IS NOT NULL
       OR ev_to_revenue IS NOT NULL
       OR ev_to_ebitda IS NOT NULL
    ORDER BY ticker
""")

rows = cur.fetchall()
logging.info(f"Found {len(rows)} symbols with ANY value data in key_metrics")

updated = 0
partial = 0

for row in rows:
    try:
        symbol = row['symbol']

        # Count how many fields are NOT NULL
        fields_count = sum([
            row['trailing_pe'] is not None,
            row['forward_pe'] is not None,
            row['price_to_sales_ttm'] is not None,
            row['price_to_book'] is not None,
            row['peg_ratio'] is not None,
            row['ev_to_revenue'] is not None,
            row['ev_to_ebitda'] is not None,
            row['dividend_yield'] is not None,
            row['payout_ratio'] is not None,
        ])

        # Update value_metrics with whatever data we have
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
            if fields_count < 3:
                partial += 1

            if updated % 100 == 0:
                logging.info(f"Updated {updated} symbols ({partial} with partial data)...")

    except Exception as e:
        conn.rollback()
        logging.error(f"Error for {row.get('symbol')}: {str(e)[:100]}")

logging.info("=" * 80)
logging.info(f"✅ SYNC COMPLETE:")
logging.info(f"   Total updated: {updated}")
logging.info(f"   With partial data: {partial}")
logging.info("=" * 80)

# Final stats
cur.execute("""
    SELECT
        COUNT(*) as total,
        COUNT(CASE WHEN trailing_pe IS NOT NULL THEN 1 END) as with_pe,
        COUNT(CASE WHEN forward_pe IS NOT NULL THEN 1 END) as with_forward_pe,
        COUNT(CASE WHEN price_to_sales_ttm IS NOT NULL THEN 1 END) as with_ps,
        COUNT(CASE WHEN price_to_book IS NOT NULL THEN 1 END) as with_pb,
        COUNT(CASE WHEN trailing_pe IS NOT NULL OR forward_pe IS NOT NULL OR price_to_sales_ttm IS NOT NULL OR price_to_book IS NOT NULL THEN 1 END) as with_any_value
    FROM value_metrics
""")

final = cur.fetchone()
logging.info(f"\nFinal Value Metrics Coverage:")
logging.info(f"  Trailing P/E:      {final['with_pe']:5d} ({100.0*final['with_pe']/final['total']:.1f}%)")
logging.info(f"  Forward P/E:       {final['with_forward_pe']:5d} ({100.0*final['with_forward_pe']/final['total']:.1f}%)")
logging.info(f"  Price/Sales:       {final['with_ps']:5d} ({100.0*final['with_ps']/final['total']:.1f}%)")
logging.info(f"  Price/Book:        {final['with_pb']:5d} ({100.0*final['with_pb']/final['total']:.1f}%)")
logging.info(f"  WITH ANY VALUE:    {final['with_any_value']:5d} ({100.0*final['with_any_value']/final['total']:.1f}%)")

conn.close()
