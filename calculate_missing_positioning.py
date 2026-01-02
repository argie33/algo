#!/usr/bin/env python3
"""
Calculate missing positioning percentages from existing holder data.
Run this to backfill positioning_metrics for stocks that have holder data but missing calculated %.
"""

import psycopg2
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def calculate_positioning_from_holders():
    conn = psycopg2.connect(
        dbname='stocks',
        user='stocks',
        password='bed0elAn',
        host='localhost'
    )
    cur = conn.cursor()

    # Find stocks with institutional holders but NULL institutional_ownership_pct
    cur.execute("""
        SELECT DISTINCT ip.symbol
        FROM institutional_positioning ip
        LEFT JOIN positioning_metrics pm ON pm.symbol = ip.symbol
        WHERE pm.institutional_ownership_pct IS NULL
        ORDER BY ip.symbol
    """)

    missing_stocks = [row[0] for row in cur.fetchall()]
    logging.info(f"Found {len(missing_stocks)} stocks with holder data but missing calculated %")

    updated = 0
    for symbol in missing_stocks:
        try:
            # Calculate institutional ownership from holders
            cur.execute("""
                SELECT SUM(shares) as total_shares
                FROM institutional_positioning
                WHERE symbol = %s
            """, (symbol,))
            result = cur.fetchone()

            if result and result[0]:
                # Get total shares outstanding from company_profile
                cur.execute("""
                    SELECT shares_outstanding
                    FROM company_profile
                    WHERE symbol = %s
                """, (symbol,))
                shares_out = cur.fetchone()

                if shares_out and shares_out[0]:
                    inst_pct = (result[0] / shares_out[0])

                    # Update positioning_metrics
                    cur.execute("""
                        UPDATE positioning_metrics
                        SET institutional_ownership_pct = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE symbol = %s
                    """, (inst_pct, symbol))

                    conn.commit()
                    updated += 1
                    logging.info(f"✅ {symbol}: Calculated institutional ownership = {inst_pct*100:.2f}%")

        except Exception as e:
            logging.error(f"❌ {symbol}: {e}")
            conn.rollback()

    logging.info(f"✅ Updated {updated}/{len(missing_stocks)} stocks")

    cur.close()
    conn.close()

if __name__ == "__main__":
    calculate_positioning_from_holders()
