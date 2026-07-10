#!/usr/bin/env python3
"""Backfill position metrics from trade data.

Fixes existing positions that were created without risk/metrics fields.
Syncs target prices, R-multiples, and other metrics from algo_trades to algo_positions.
"""

import logging
import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def backfill_position_metrics():
    """Backfill position metrics from trades for positions missing data."""
    conn = psycopg2.connect(
        dbname="stocks",
        user="postgres",
        password="password",
        host="localhost",
        port="5432"
    )
    cur = conn.cursor(cursor_factory=RealDictCursor)
    updated_count = 0

    try:
        # Find all open positions missing metrics
        cur.execute("""
            SELECT
                ap.position_id, ap.symbol, ap.quantity, ap.entry_price,
                ap.stop_loss_price,
                at.trade_id, at.target_1_price, at.target_1_r_multiple,
                at.target_2_price, at.target_2_r_multiple,
                at.target_3_price, at.target_3_r_multiple,
                at.sector, at.industry, at.rs_percentile
            FROM algo_positions ap
            LEFT JOIN algo_trades at ON ap.symbol = at.symbol
                AND at.status IN ('open', 'filled', 'partially_filled')
            WHERE ap.status IN ('open', 'paper_open')
            AND (ap.target_1_price IS NULL OR ap.r_multiple IS NULL OR ap.metrics_updated_at IS NULL)
            ORDER BY ap.entry_date DESC
        """)
        positions_to_update = cur.fetchall()
        logger.info(f"Found {len(positions_to_update)} positions needing metric backfill")

        for pos in positions_to_update:
            if not pos['trade_id']:
                logger.warning(f"Position {pos['position_id']} ({pos['symbol']}) has no matching trade")
                continue

            # Calculate R-multiple
            r_multiple = None
            if pos['entry_price'] and pos['stop_loss_price']:
                risk_per_share = float(pos['entry_price']) - float(pos['stop_loss_price'])
                if risk_per_share > 0:
                    r_multiple = 1.0

            logger.info(
                f"Updating {pos['symbol']}: target_1={pos['target_1_price']} "
                f"(R {pos['target_1_r_multiple']}), sector={pos['sector']}"
            )

            # Update position with trade metrics
            cur.execute("""
                UPDATE algo_positions
                SET
                    target_1_price = %s,
                    target_2_price = %s,
                    target_3_price = %s,
                    target_1_r_multiple = %s,
                    target_2_r_multiple = %s,
                    target_3_r_multiple = %s,
                    r_multiple = %s,
                    metrics_updated_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE position_id = %s
            """, (
                pos['target_1_price'],
                pos['target_2_price'],
                pos['target_3_price'],
                pos['target_1_r_multiple'],
                pos['target_2_r_multiple'],
                pos['target_3_r_multiple'],
                r_multiple,
                pos['position_id'],
            ))
            updated_count += 1

        conn.commit()
        logger.info(f"✓ Backfilled metrics for {updated_count} positions")

        # Verify backfill
        cur.execute("""
            SELECT COUNT(*) as count
            FROM algo_positions
            WHERE status IN ('open', 'paper_open')
            AND target_1_price IS NOT NULL
            AND r_multiple IS NOT NULL
            AND metrics_updated_at IS NOT NULL
        """)
        verified = cur.fetchone()
        logger.info(f"✓ Verified: {verified['count']} positions now have complete metrics")

    except Exception as e:
        logger.error(f"Backfill failed: {e}")
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    backfill_position_metrics()
