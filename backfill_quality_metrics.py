#!/usr/bin/env python3
"""
Backfill quality_metrics for all symbols with complete financial data.

Quality metrics require overlap of income statement + balance sheet data.
Currently only 4 rows present; this script will calculate for all ~350 eligible symbols.
"""

import psycopg2
from pathlib import Path
from dotenv import load_dotenv
import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

def _get_db_config():
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 5432)),
        "user": os.getenv("DB_USER", "stocks"),
        "password": os.getenv("DB_PASSWORD", ""),
        "database": os.getenv("DB_NAME", "stocks"),
    }

def backfill_quality_metrics():
    """Calculate quality metrics for all symbols with complete financial data."""
    conn = psycopg2.connect(**_get_db_config())
    cur = conn.cursor()

    try:
        # Find symbols with both income statement and balance sheet data
        cur.execute('''
            SELECT DISTINCT a.symbol
            FROM annual_income_statement a
            INNER JOIN annual_balance_sheet b ON a.symbol = b.symbol AND a.fiscal_year = b.fiscal_year
            WHERE a.gross_profit IS NOT NULL
            AND a.operating_income IS NOT NULL
            AND a.net_income IS NOT NULL
            AND b.total_assets IS NOT NULL
            AND b.total_liabilities IS NOT NULL
            ORDER BY a.symbol
        ''')
        symbols = [row[0] for row in cur.fetchall()]
        logger.info(f"Found {len(symbols)} symbols with complete financial data")

        inserted = 0
        skipped = 0

        for i, symbol in enumerate(symbols):
            if (i + 1) % 50 == 0:
                logger.info(f"  Progress: {i+1}/{len(symbols)}")

            try:
                # Get latest annual financial data
                cur.execute('''
                    SELECT
                        a.fiscal_year,
                        a.gross_profit / NULLIF(a.revenue, 0) * 100 as gross_margin,
                        a.operating_income / NULLIF(a.revenue, 0) * 100 as operating_margin,
                        a.net_income / NULLIF(a.revenue, 0) * 100 as net_margin,
                        b.total_assets / NULLIF(a.revenue, 0) as asset_turnover,
                        a.net_income / NULLIF(b.total_assets, 0) * 100 as roa,
                        a.net_income / NULLIF(b.stockholders_equity, 0) * 100 as roe
                    FROM annual_income_statement a
                    INNER JOIN annual_balance_sheet b ON a.symbol = b.symbol AND a.fiscal_year = b.fiscal_year
                    WHERE a.symbol = %s
                    AND a.gross_profit IS NOT NULL
                    AND a.net_income IS NOT NULL
                    AND b.stockholders_equity IS NOT NULL
                    ORDER BY a.fiscal_year DESC
                    LIMIT 1
                ''', (symbol,))

                row = cur.fetchone()
                if not row:
                    skipped += 1
                    continue

                fiscal_year, gross_margin, op_margin, net_margin, asset_turnover, roa, roe = row

                # Insert or update quality metrics
                cur.execute('''
                    INSERT INTO quality_metrics (
                        symbol, fiscal_year,
                        gross_margin, operating_margin, net_margin,
                        asset_turnover, roa, roe,
                        created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (symbol, fiscal_year) DO UPDATE SET
                        gross_margin = EXCLUDED.gross_margin,
                        operating_margin = EXCLUDED.operating_margin,
                        net_margin = EXCLUDED.net_margin,
                        asset_turnover = EXCLUDED.asset_turnover,
                        roa = EXCLUDED.roa,
                        roe = EXCLUDED.roe,
                        updated_at = CURRENT_TIMESTAMP
                ''', (symbol, fiscal_year, gross_margin, op_margin, net_margin, asset_turnover, roa, roe))

                inserted += 1

            except Exception as e:
                logger.debug(f"Error processing {symbol}: {e}")
                skipped += 1
                continue

        conn.commit()
        logger.info(f"Successfully inserted {inserted} quality metrics records (skipped {skipped})")

        # Verify
        cur.execute('SELECT COUNT(*) FROM quality_metrics')
        final_count = cur.fetchone()[0]
        logger.info(f"Final quality_metrics count: {final_count}")

        return True

    except Exception as e:
        logger.error(f"Error in backfill: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    success = backfill_quality_metrics()
    sys.exit(0 if success else 1)
